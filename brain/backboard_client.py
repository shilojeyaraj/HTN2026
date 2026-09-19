"""Thin wrapper around the Backboard SDK: one persistent thread/assistant across ticks.

SDK verified against backboard-sdk v1.5.19:
- send_message returns ChatMessagesResponse (convenience properties proxy to last message)
- submit_tool_outputs_simple takes thread_id + tool_outputs list
- input_image= for vision (not files=)
- call.function.arguments is a JSON string (not parsed_arguments)
"""

import asyncio
import json
import os
import threading

from backboard import BackboardClient

MAX_TOOL_ROUNDS = 6

ENCOUNTERS = [
    {"id": "ENC-2026-0147", "status": "RESCUED", "sector": "7-A", "location": "Sector 7-A, Riverside Apartments, Block A", "duration": "42 minutes", "location_type": "residential"},
    {"id": "ENC-2026-0146", "status": "LOCATED", "sector": "4-C", "location": "Sector 4-C, Harbor Warehouse 12", "duration": "27 minutes", "location_type": "industrial"},
    {"id": "ENC-2026-0145", "status": "NO CONTACT", "sector": "2-D", "location": "Sector 2-D, Old Mill Road, Residential", "duration": "11 minutes", "location_type": "residential"},
    {"id": "ENC-2026-0144", "status": "RESCUED", "sector": "9-F", "location": "Sector 9-F, Northgate Transit Tunnel", "duration": "65 minutes", "location_type": "transit"},
    {"id": "ENC-2026-0143", "status": "LOCATED", "sector": "5-B", "location": "Sector 5-B, Grainview School, Gymnasium", "duration": "33 minutes", "location_type": "public"},
    {"id": "ENC-2026-0142", "status": "RESCUED", "sector": "1-A", "location": "Sector 1-A, Civic Center Parking Deck", "duration": "51 minutes", "location_type": "parking"},
    {"id": "ENC-2026-0141", "status": "NO CONTACT", "sector": "3-E", "location": "Sector 3-E, Lakeside Trailer Park", "duration": "9 minutes", "location_type": "residential"},
    {"id": "ENC-2026-0140", "status": "RESCUED", "sector": "6-C", "location": "Sector 6-C, Fairmount Hospital, East Wing", "duration": "83 minutes", "location_type": "medical"},
]


class BackboardBrain:
    def __init__(self, llm_provider: str, model_name: str):
        self.client = BackboardClient(api_key=os.environ["BACKBOARD_API_KEY"])
        self.llm_provider = llm_provider
        self.model_name = model_name
        self.thread_id = None
        self.assistant_id = None
        self._knowledge_uploaded = False
        self._encounters_loaded = False

    async def _run_tools(self, content: str, system_prompt: str, tools: list[dict], execute_tool, memory: str) -> list:
        await self._ensure_initialized()
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
                args = json.loads(call.function.arguments)
                result = execute_tool(call.function.name, args)
                results.append({"name": call.function.name, "arguments": args, "result": result})
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
            input_image=image_path,
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

    async def _ensure_initialized(self) -> None:
        """Create the assistant, upload knowledge base + encounter history for RAG, load encounters into memory."""
        if self.assistant_id is None:
            assistant = await self.client.create_assistant(name="rescue-rover-brain")
            self.assistant_id = assistant.id
        if not self._knowledge_uploaded:
            kb_dir = os.path.join(os.path.dirname(__file__), "..", "knowledge")
            for doc in ["rescue_protocols.md", "encounter_history.md"]:
                path = os.path.join(kb_dir, doc)
                if os.path.exists(path):
                    try:
                        await self.client.upload_document_to_assistant(self.assistant_id, path)
                    except Exception:
                        pass
            self._knowledge_uploaded = True
        if not self._encounters_loaded:
            for enc in ENCOUNTERS:
                try:
                    await self.client.add_memory(
                        self.assistant_id,
                        f"{enc['id']}: {enc['status']} at {enc['location']}. Duration: {enc['duration']}.",
                        metadata={"type": "encounter", "encounter_id": enc["id"], "sector": enc["sector"], "status": enc["status"]},
                    )
                except Exception:
                    pass
            self._encounters_loaded = True

    async def _search_memory(self, query: str) -> dict:
        await self._ensure_initialized()
        return await self.client.search_memories(self.assistant_id, query, limit=5)

    async def _log_finding(self, finding_type: str, description: str) -> dict:
        await self._ensure_initialized()
        return await self.client.add_memory(
            self.assistant_id,
            f"[{finding_type}] {description}",
            metadata={"type": finding_type},
        )

    def search_memory(self, query: str) -> dict:
        """Search mission memory and knowledge base. Thread-safe: runs in a new event loop."""
        result = [{}]
        def _worker():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result[0] = loop.run_until_complete(self._search_memory(query))
            except Exception:
                pass
            finally:
                loop.close()
        t = threading.Thread(target=_worker)
        t.start()
        t.join()
        return result[0]

    def log_finding(self, finding_type: str, description: str) -> dict:
        """Log a mission finding to persistent memory. Thread-safe."""
        result = [{}]
        def _worker():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result[0] = loop.run_until_complete(self._log_finding(finding_type, description))
            except Exception:
                pass
            finally:
                loop.close()
        t = threading.Thread(target=_worker)
        t.start()
        t.join()
        return result[0]

    async def _get_insights(self) -> dict:
        await self._ensure_initialized()
        return await self.client.get_memory_insights(self.assistant_id)

    def get_insights(self) -> dict:
        """Analyze patterns across all stored mission memory. Thread-safe."""
        result = [{}]
        def _worker():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                result[0] = loop.run_until_complete(self._get_insights())
            except Exception:
                pass
            finally:
                loop.close()
        t = threading.Thread(target=_worker)
        t.start()
        t.join()
        return result[0]


# Shared across the deliberative loop (brain/loop.py) so repeated episodes ride the same
# mission thread — that's what makes `memory="Auto"` and shared history useful. Voice is
# direct (voice/tts.py = ElevenLabs, voice/stt.py = Baseten), not routed through here --
# TTS reverted from Backboard-routed for testability (BUILD_PLAN.md).
# VERIFY: current routable Gemini slug on Backboard (BUILD_PLAN.md section 4).
brain = BackboardBrain(llm_provider="google", model_name="gemini-2.5-pro")
