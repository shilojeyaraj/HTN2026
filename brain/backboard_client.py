"""Thin wrapper around the Backboard SDK: one persistent thread/assistant across ticks.

SDK verified against backboard-sdk v1.5.19:
- send_message returns ChatMessagesResponse (convenience properties proxy to last message)
- submit_tool_outputs_simple takes thread_id + tool_outputs list
- call.function.arguments is a JSON string (not parsed_arguments)
"""

import asyncio
import json
import logging
import os
import re
import time

from backboard import BackboardClient

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6
MAX_RATE_LIMIT_RETRIES = 3
MAX_RETRY_BACKOFF_S = 8.0
RETRY_DELAY_RE = re.compile(
    r"(?:retry[_ ]?delay|retry\s+(?:in|after))\D*(\d+(?:\.\d+)?)\s*(ms|s|seconds)?",
    re.IGNORECASE,
)


class BackboardBrain:
    def __init__(self, llm_provider: str, model_name: str):
        self.client = None
        self.llm_provider = llm_provider
        self.model_name = model_name
        self.thread_id = None
        self.assistant_id = None
        self._knowledge_uploaded = False

    def _get_client(self) -> BackboardClient:
        if self.client is None:
            self.client = BackboardClient(api_key=os.environ["BACKBOARD_API_KEY"], timeout=120)
        return self.client

    async def aclose(self) -> None:
        """Close the long-lived Backboard client during application shutdown."""
        client, self.client = self.client, None
        if client is not None:
            await client.aclose()

    @staticmethod
    def _message(response) -> dict:
        messages = getattr(response, "messages", None) or []
        return messages[-1] if messages else {}

    @classmethod
    def _is_llm_error(cls, response) -> bool:
        content = str(cls._message(response).get("content") or "").lower()
        return any(marker in content for marker in ("llm invocation error", "resource_exhausted", "rate limit", "429"))

    @classmethod
    def _is_rate_limited(cls, response) -> bool:
        content = str(cls._message(response).get("content") or "").lower()
        return "resource_exhausted" in content or "rate limit" in content or "429" in content

    @staticmethod
    def _retry_delay(content: str, attempt: int) -> float:
        match = RETRY_DELAY_RE.search(content)
        if match:
            delay = float(match.group(1))
            if (match.group(2) or "").lower() == "ms":
                delay /= 1000
            return max(delay, min(2 ** attempt, MAX_RETRY_BACKOFF_S))
        return min(2 ** attempt, MAX_RETRY_BACKOFF_S)

    @classmethod
    def _log_response(cls, response, elapsed_s: float) -> None:
        message = cls._message(response)
        tool_calls = message.get("tool_calls") or []
        retrieved_memories = message.get("retrieved_memories") or []
        logger.info("Backboard planner: response latency=%.2fs", elapsed_s)
        logger.info("Backboard planner: assistant content=%s", message.get("content"))
        logger.info("Backboard planner: tool calls=%d", len(tool_calls))
        logger.info("Backboard planner: retrieved memories=%d", len(retrieved_memories))
        logger.info("Backboard planner: llm_error=%s", cls._is_llm_error(response))

    async def _request_planner(self, content: str, system_prompt: str, tools: list[dict], memory: str):
        thread_id, assistant_id = self.thread_id, self.assistant_id
        for attempt in range(MAX_RATE_LIMIT_RETRIES + 1):
            logger.info("Backboard planner: request start model=%s", self.model_name)
            started = time.monotonic()
            response = await self._get_client().send_message(
                content=content,
                system_prompt=system_prompt,
                llm_provider=self.llm_provider,
                model_name=self.model_name,
                tools=tools,
                thread_id=thread_id,
                assistant_id=assistant_id,
                memory=memory,
            )
            self._log_response(response, time.monotonic() - started)
            thread_id = response.thread_id or thread_id
            assistant_id = response.assistant_id or assistant_id
            if not self._is_rate_limited(response) or attempt == MAX_RATE_LIMIT_RETRIES:
                self.thread_id, self.assistant_id = thread_id, assistant_id
                return response
            await asyncio.sleep(self._retry_delay(response.content or "", attempt))

    async def _run_tools(self, content: str, system_prompt: str, tools: list[dict], execute_tool, memory: str) -> list:
        await self._ensure_initialized()
        response = await self._request_planner(content, system_prompt, tools, memory)
        if response.status == "FAILED" or self._is_llm_error(response):
            return []

        # Inner Monologue (CLAUDE.md section 7): feed each verb's REAL execution result
        # back to the model, not a trivial ack, so it can react to a failed or completed
        # command within this same episode. Capped so a
        # misbehaving chain can't loop forever.
        results = []
        rounds = 0
        while response.status == "REQUIRES_ACTION" and rounds < MAX_TOOL_ROUNDS:
            tool_outputs = []
            for call in response.tool_calls:
                args = json.loads(call.function.arguments)
                logger.info("Backboard planner: executing %s(%s)", call.function.name, args)
                result = execute_tool(call.function.name, args)
                results.append({"name": call.function.name, "arguments": args, "result": result})
                tool_outputs.append({"tool_call_id": call.id, "output": json.dumps(result)})

            started = time.monotonic()
            response = await self._get_client().submit_tool_outputs_simple(
                thread_id=response.thread_id, tool_outputs=tool_outputs,
            )
            self._log_response(response, time.monotonic() - started)
            if response.status == "FAILED" or self._is_llm_error(response):
                return results
            rounds += 1

        return results

    async def run_tools(self, content: str, system_prompt: str, tools: list[dict], execute_tool, memory: str = "off") -> list:
        return await self._run_tools(content, system_prompt, tools, execute_tool, memory)

    async def _ensure_initialized(self) -> None:
        """Create static assistant data without waiting for document indexing."""
        client = self._get_client()
        if self.assistant_id is None:
            assistant = await client.create_assistant(name="rescue-rover-brain")
            self.assistant_id = assistant.assistant_id
        if not self._knowledge_uploaded:
            kb_dir = os.path.join(os.path.dirname(__file__), "..", "knowledge")
            for doc in ["rescue_protocols.md"]:
                path = os.path.join(kb_dir, doc)
                if os.path.exists(path):
                    try:
                        await client.upload_document_to_assistant(self.assistant_id, path)
                    except Exception:
                        pass
            self._knowledge_uploaded = True

    async def _search_memory(self, query: str) -> dict:
        await self._ensure_initialized()
        return await self._get_client().search_memories(self.assistant_id, query, limit=5)

    async def _log_finding(self, finding_type: str, description: str) -> dict:
        await self._ensure_initialized()
        return await self._get_client().add_memory(
            self.assistant_id,
            f"[{finding_type}] {description}",
            metadata={"type": finding_type},
        )

    async def search_memory(self, query: str) -> dict:
        return await self._search_memory(query)

    async def log_finding(self, finding_type: str, description: str) -> dict:
        return await self._log_finding(finding_type, description)

    async def _get_insights(self) -> dict:
        await self._ensure_initialized()
        return await self._get_client().get_memory_insights(self.assistant_id)

    async def get_insights(self) -> dict:
        return await self._get_insights()


# Shared across the deliberative loop (brain/loop.py) so repeated episodes ride the same
# mission thread — that's what makes `memory="Auto"` and shared history useful. Voice is
# direct (voice/tts.py = ElevenLabs, voice/stt.py = Baseten), not routed through here --
# TTS reverted from Backboard-routed for testability (BUILD_PLAN.md).
# VERIFY: current routable Gemini slug on Backboard (BUILD_PLAN.md section 4).
brain = BackboardBrain(llm_provider="google", model_name="gemini-3.5-flash")
