"""Integration test for the Backboard brain (brain/backboard_client.py).

Hits the real Backboard API. Requires BACKBOARD_API_KEY in .env.
Run: pytest -m integration -k backboard
"""

import os
import pytest

from tests.conftest import has_real_key

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not has_real_key("BACKBOARD_API_KEY"), reason="BACKBOARD_API_KEY not set in .env"),
]


@pytest.mark.asyncio
async def test_backboard_send_message_returns_response():
    from backboard import BackboardClient

    client = BackboardClient(api_key=os.environ["BACKBOARD_API_KEY"])
    response = await client.send_message(
        content="Say 'rescue rover online' and nothing else.",
        llm_provider="google",
        model_name="gemini-2.5-flash",
        memory="off",
    )
    assert response.content is not None
    assert len(response.content) > 0
    assert response.thread_id is not None
    print(f"\n  Backboard reply: {response.content[:200]}")
    print(f"  Thread ID: {response.thread_id}")


@pytest.mark.asyncio
async def test_backboard_tool_calling_roundtrip():
    """Send a message with a simple tool and verify the REQUIRES_ACTION flow."""
    from backboard import BackboardClient

    client = BackboardClient(api_key=os.environ["BACKBOARD_API_KEY"])
    tools = [
        {
            "type": "function",
            "function": {
                "name": "get_state",
                "description": "Read the robot's current pose, velocity, and goal.",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    response = await client.send_message(
        content="What is the robot's current state? Call get_state.",
        llm_provider="google",
        model_name="gemini-2.5-flash",
        tools=tools,
        memory="off",
    )
    # The model should either respond directly or request a tool call
    if response.status == "REQUIRES_ACTION":
        assert response.tool_calls is not None
        assert len(response.tool_calls) > 0
        call = response.tool_calls[0]
        assert call.function.name == "get_state"
        import json
        args = json.loads(call.function.arguments)
        assert args == {} or args == {}
        print(f"\n  Tool call: {call.function.name}({call.function.arguments})")

        # Submit a tool output and verify we get a final response
        response2 = await client.submit_tool_outputs_simple(
            thread_id=response.thread_id,
            tool_outputs=[{"tool_call_id": call.id, "output": json.dumps({"pose": [0, 0, 0], "velocity": [0, 0]})}],
        )
        assert response2.content is not None
        print(f"  Final reply: {response2.content[:200]}")
    else:
        print(f"\n  Model replied directly (no tool call): {response.content[:200]}")
