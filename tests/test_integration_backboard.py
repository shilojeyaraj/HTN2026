"""Live Backboard text/tool round trip; no robot or speech hardware is used.

Run: pytest -q -m integration tests/test_integration_backboard.py
"""

import asyncio
import os

import pytest

from brain.backboard_client import BackboardBrain
from brain.tools import validate_tool_args
from tests.conftest import has_real_key

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not has_real_key("BACKBOARD_API_KEY"), reason="BACKBOARD_API_KEY not set in .env"),
]


def test_backboard_text_and_tool_roundtrip():
    async def check():
        planner = BackboardBrain(
            os.getenv("BACKBOARD_PROVIDER", "openai"),
            os.getenv("BACKBOARD_MODEL", "gpt-4.1"),
            fallback_provider=os.getenv("BACKBOARD_FALLBACK_PROVIDER", "openai"),
            fallback_model=os.getenv("BACKBOARD_FALLBACK_MODEL", ""),
        )
        try:
            await planner._ensure_initialized()
            response = await planner._request_planner("Say 'rescue rover online' only.", "Be concise.", [], "off")
            # HTTP 200 with embedded LLM errors used to incorrectly pass this test.
            assert not planner._is_llm_error(response), response.content
            assert response.status == "COMPLETED" and response.content
            assert response.thread_id

            def simulated_state(name, args):
                assert name == "get_state"
                assert validate_tool_args(name, args) == {}
                return {"status": "completed", "simulation": True}

            results = await planner.run_tools(
                "Call get_state exactly once, then summarize its result.",
                "This is a diagnostic with simulated telemetry. Use the requested tool.",
                [{"type": "function", "function": {
                    "name": "get_state", "description": "Read simulated robot state.",
                    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                }}],
                simulated_state,
            )
            assert len(results) == 1 and results[0]["name"] == "get_state"
            assert planner._pending_tool_outputs is None
        finally:
            await planner.aclose()

    asyncio.run(check())
