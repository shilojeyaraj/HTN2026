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
import time

from backboard import BackboardClient
from backboard.exceptions import BackboardAPIError

from brain.tools import PHYSICAL_ACTIONS
from shared.inference import InferenceUnavailable, is_daily_quota, is_rate_limited, retry_delay

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 6
MAX_RATE_LIMIT_RETRIES = 3


class BackboardBrain:
    def __init__(self, llm_provider: str, model_name: str, *, fallback_provider="openai", fallback_model="gpt-4.1-mini"):
        self.client = None
        self.llm_provider = llm_provider
        self.model_name = model_name
        self.thread_id = None
        self.assistant_id = None
        self._pending_tool_outputs = None
        self._fallback = (fallback_provider, fallback_model)
        self._unavailable = None

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
        return response.status == "FAILED" or "llm invocation error" in content or is_rate_limited(content)

    @classmethod
    def _is_rate_limited(cls, response) -> bool:
        content = str(cls._message(response).get("content") or "").lower()
        return is_rate_limited(content)

    @classmethod
    def _log_response(cls, response, elapsed_s: float) -> None:
        message = cls._message(response)
        tool_calls = message.get("tool_calls") or []
        retrieved_memories = message.get("retrieved_memories") or []
        logger.info("Backboard planner: response latency=%.2fs", elapsed_s)
        logger.info("Backboard planner: assistant content=%s", message.get("content"))
        logger.info("Backboard planner: tool calls=%d", len(tool_calls) if isinstance(tool_calls, list) else 0)
        logger.info("Backboard planner: retrieved memories=%d", len(retrieved_memories))
        logger.info("Backboard planner: llm_error=%s", cls._is_llm_error(response))
        for call in tool_calls if isinstance(tool_calls, list) else []:
            function = call.get("function") if isinstance(call, dict) else None
            if isinstance(function, dict):
                logger.info("Backboard planner: tool=%s args=%r", function.get("name"), function.get("arguments"))

    async def _request_planner(self, content: str, system_prompt: str, tools: list[dict], memory: str, tool_outputs=None):
        if self._unavailable:
            raise InferenceUnavailable(self._unavailable)
        attempt = 0
        retry_content = content
        if tool_outputs:
            retry_content += "\nAlready processed tool results (do not repeat these actions):\n" + json.dumps(tool_outputs)
        while True:
            logger.info("Backboard planner: request start provider=%s model=%s%s", self.llm_provider, self.model_name,
                        " (tool results)" if tool_outputs else "")
            started = time.monotonic()
            retry_after = None
            try:
                if tool_outputs:
                    response = await self._get_client().submit_tool_outputs_simple(
                        thread_id=self.thread_id, tool_outputs=tool_outputs,
                    )
                else:
                    response = await self._get_client().send_message(
                        content=content, system_prompt=system_prompt,
                        llm_provider=self.llm_provider, model_name=self.model_name,
                        tools=tools, thread_id=self.thread_id,
                        assistant_id=self.assistant_id, memory=memory,
                    )
                self._log_response(response, time.monotonic() - started)
                self.thread_id = response.thread_id or self.thread_id
                self.assistant_id = response.assistant_id or self.assistant_id
                if not self._is_rate_limited(response):
                    return response
                error = response.content or ""
                # HTTP 200 accepted the outputs; the provider failed afterwards.
                # Retry inference as a message, never resubmit consumed tool IDs.
                tool_outputs = None
                content = retry_content
            except BackboardAPIError as exc:
                if exc.status_code != 429 and not is_rate_limited(exc):
                    raise
                error = str(exc)
                if exc.response is not None:
                    retry_after = exc.response.headers.get("Retry-After")
                logger.warning("Backboard planner: rate limited: %s", error)

            daily = is_daily_quota(error)
            if daily or attempt >= MAX_RATE_LIMIT_RETRIES:
                provider, model = self._fallback
                if not tool_outputs and model and (self.llm_provider, self.model_name) != self._fallback:
                    logger.warning("Backboard planner: %s for %s; switching to %s/%s for this session",
                                   "daily quota exhausted" if daily else "retries exhausted",
                                   self.model_name, provider, model)
                    self.llm_provider, self.model_name = provider, model
                    attempt = 0
                    # A continuation cannot choose a model. Resume via send_message.
                    tool_outputs = None
                    content = retry_content
                    continue
                self._unavailable = (f"Planner quota unavailable for {self.model_name}. "
                                     "Check provider billing/quota or configure BACKBOARD_MODEL and BACKBOARD_PROVIDER. "
                                     "No further actions will execute.")
                raise InferenceUnavailable(self._unavailable)
            delay = retry_delay(error, attempt, retry_after)
            logger.warning("Backboard planner: retry %d/%d in %.1fs; holding current scene/state, no action",
                           attempt + 1, MAX_RATE_LIMIT_RETRIES, delay)
            await asyncio.sleep(delay)
            attempt += 1

    async def _run_tools(self, content: str, system_prompt: str, tools: list[dict], execute_tool, memory: str) -> list:
        await self._ensure_initialized()
        if self._pending_tool_outputs:
            # The SDK resumes planning when outputs are submitted. Wait until this
            # cycle has perceived again, then include that scene in the tool feedback.
            outputs = [dict(output) for output in self._pending_tool_outputs]
            last_result = json.loads(outputs[-1]["output"])
            last_result["current_scene_and_state"] = content
            outputs[-1]["output"] = json.dumps(last_result)
            response = await self._request_planner(content, system_prompt, tools, memory, outputs)
            self._pending_tool_outputs = None
        else:
            response = await self._request_planner(content, system_prompt, tools, memory)
        if response.status == "FAILED" or self._is_llm_error(response):
            return []

        results = []
        rounds = 0
        while response.status == "REQUIRES_ACTION" and rounds < MAX_TOOL_ROUNDS:
            tool_outputs = []
            physical_attempted = False
            # Read raw calls so malformed argument JSON or SDK ToolCall validation
            # cannot throw before the executor has a chance to reject the call.
            calls = self._message(response).get("tool_calls")
            if not isinstance(calls, list) or not calls:
                logger.error("Rejected malformed tool_calls=%r", calls)
                return results
            for call in calls:
                if not isinstance(call, dict) or not isinstance(call.get("id"), str) or not call.get("id"):
                    logger.error("Rejected tool call without a valid id: %r", call)
                    continue
                function = call.get("function")
                name = function.get("name") if isinstance(function, dict) else None
                args = function.get("arguments") if isinstance(function, dict) else function
                if physical_attempted:
                    result = {"status": "skipped", "detail": "Not executed: replan after fresh perception."}
                    logger.info("Skipped tool=%s args=%r: awaiting fresh perception", name, args)
                else:
                    result = execute_tool(name, args)
                    results.append({"name": name, "arguments": args, "result": result})
                    physical_attempted = (
                        isinstance(name, str) and name in PHYSICAL_ACTIONS
                        and result.get("status") != "rejected"
                    )
                tool_outputs.append({"tool_call_id": call["id"], "output": json.dumps(result)})

            if not tool_outputs:
                return results
            rounds += 1
            if physical_attempted or rounds == MAX_TOOL_ROUNDS:
                self._pending_tool_outputs = tool_outputs
                return results
            response = await self._request_planner(content, system_prompt, tools, memory, tool_outputs)
            if response.status == "FAILED" or self._is_llm_error(response):
                return results

        return results

    async def run_tools(self, content: str, system_prompt: str, tools: list[dict], execute_tool, memory: str = "off") -> list:
        return await self._run_tools(content, system_prompt, tools, execute_tool, memory)

    async def _ensure_initialized(self) -> None:
        """Create the assistant without uploading or indexing documents."""
        client = self._get_client()
        if self.assistant_id is None:
            assistant = await client.create_assistant(name="rescue-rover-brain")
            self.assistant_id = assistant.assistant_id

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
brain = BackboardBrain(
    llm_provider=os.getenv("BACKBOARD_PROVIDER", "google"),
    model_name=os.getenv("BACKBOARD_MODEL", "gemini-3.6-flash"),
    fallback_provider=os.getenv("BACKBOARD_FALLBACK_PROVIDER", "openai"),
    fallback_model=os.getenv("BACKBOARD_FALLBACK_MODEL", "gpt-4.1-mini"),
)
