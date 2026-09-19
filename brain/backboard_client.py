"""Thin wrapper around the Backboard SDK: one persistent thread/assistant across ticks.

VERIFY (BACKBOARD.md section 12): confirm `send_message`/`submit_tool_outputs_simple`
signatures against the installed `backboard-sdk` version before relying on this.
"""

import asyncio
import json
import os

from backboard import BackboardClient

MAX_TOOL_ROUNDS = 6


class BackboardBrain:
    def __init__(self, llm_provider: str, model_name: str):
        self.client = BackboardClient(api_key=os.environ["BACKBOARD_API_KEY"])
        self.llm_provider = llm_provider
        self.model_name = model_name
        self.thread_id = None
        self.assistant_id = None

    async def _run_tools(self, content: str, system_prompt: str, tools: list[dict], execute_tool, memory: str) -> list:
        response = await self.client.send_message(
            content=content,
            system_prompt=system_prompt,
            llm_provider=self.llm_provider,
            model_name=self.model_name,
            tools=tools,
            thread_id=self.thread_id,
            assistant_id=self.assistant_id,
            memory=memory,
        )
        self.thread_id = response.thread_id
        self.assistant_id = response.assistant_id

        # Inner Monologue (CLAUDE.md section 7): feed each verb's REAL execution result
        # back to the model, not a trivial ack, so it can react (e.g. turn() after a
        # forward() that stopped_by_obstacle) within this same episode. Capped so a
        # misbehaving chain can't loop forever.
        results = []
        rounds = 0
        while response.status == "REQUIRES_ACTION" and rounds < MAX_TOOL_ROUNDS:
            tool_outputs = []
            for call in response.tool_calls:
                result = execute_tool(call.function.name, call.function.parsed_arguments)
                results.append({"name": call.function.name, "arguments": call.function.parsed_arguments, "result": result})
                tool_outputs.append({"tool_call_id": call.id, "output": json.dumps(result)})

            response = await self.client.submit_tool_outputs_simple(
                thread_id=response.thread_id, tool_outputs=tool_outputs,
            )
            rounds += 1

        return results

    def run_tools(self, content: str, system_prompt: str, tools: list[dict], execute_tool, memory: str = "off") -> list:
        return asyncio.run(self._run_tools(content, system_prompt, tools, execute_tool, memory))

    async def _describe(self, content: str, image_path: str, llm_provider: str, model_name: str) -> str:
        response = await self.client.send_message(
            content=content,
            files=[image_path],  # VERIFY: SDK's files= kwarg vs. raw HTTP multipart (BACKBOARD.md section 12)
            llm_provider=llm_provider,
            model_name=model_name,
            thread_id=self.thread_id,
            assistant_id=self.assistant_id,
        )
        self.thread_id = response.thread_id
        self.assistant_id = response.assistant_id
        return response.content

    def describe(self, content: str, image_path: str, llm_provider: str = "google", model_name: str = "gemini-2.5-flash") -> str:
        return asyncio.run(self._describe(content, image_path, llm_provider, model_name))


# Shared across the deliberative loop (brain/loop.py) so repeated episodes ride the same
# mission thread — that's what makes `memory="Auto"` and shared history useful. Voice is
# direct (voice/tts.py = ElevenLabs, voice/stt.py = Baseten), not routed through here --
# TTS reverted from Backboard-routed for testability (BUILD_PLAN.md).
# VERIFY: current routable Gemini slug on Backboard (BUILD_PLAN.md section 4).
brain = BackboardBrain(llm_provider="google", model_name="gemini-2.5-pro")
