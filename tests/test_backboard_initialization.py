"""Backboard planner setup never uploads documents."""

import asyncio
import logging
from types import SimpleNamespace

from brain import backboard_client
from brain.backboard_client import BackboardBrain


class FakeClient:
    def __init__(self):
        self.uploaded = []
        self.memories = []

    async def create_assistant(self, **_kwargs):
        return SimpleNamespace(assistant_id="assistant")

    async def upload_document_to_assistant(self, assistant_id, path):
        self.uploaded.append((assistant_id, path))

    async def add_memory(self, assistant_id, content, metadata):
        self.memories.append((assistant_id, content, metadata))


def test_planner_setup_does_not_upload_documents():
    brain = object.__new__(BackboardBrain)
    brain.client = FakeClient()
    brain.assistant_id = None

    asyncio.run(brain._ensure_initialized())

    assert brain.client.uploaded == []
    assert brain.client.memories == []


def test_backboard_client_closes_once_at_shutdown():
    class ClosingClient:
        closed = 0

        async def aclose(self):
            self.closed += 1

    brain = object.__new__(BackboardBrain)
    brain.client = ClosingClient()

    asyncio.run(brain.aclose())

    assert brain.client is None


def test_planner_response_logs_only_operational_fields(caplog):
    class FailedResponse:
        status = "COMPLETED"
        messages = [{
            "content": "Ready to move.",
            "tool_calls": [{"id": "call-1"}],
            "retrieved_memories": [{"id": "mission-memory"}],
        }]

    with caplog.at_level(logging.INFO):
        BackboardBrain._log_response(FailedResponse(), 0.1)

    assert "response latency=0.10s" in caplog.text
    assert "assistant content=Ready to move." in caplog.text
    assert "tool calls=1" in caplog.text
    assert "retrieved memories=1" in caplog.text
    assert "llm_error=False" in caplog.text
    assert "FailedResponse" not in caplog.text


def test_rate_limit_retries_planning_without_executing_a_tool(monkeypatch):
    def response(content, thread_id="thread"):
        return SimpleNamespace(
            status="COMPLETED",
            content=content,
            thread_id=thread_id,
            assistant_id="assistant",
            messages=[{"content": content, "tool_calls": [], "retrieved_memories": []}],
        )

    class RetryClient:
        def __init__(self):
            self.requests = []

        async def send_message(self, **kwargs):
            self.requests.append(kwargs)
            if len(self.requests) == 1:
                return response("LLM invocation error: 429 RESOURCE_EXHAUSTED; retryDelay: 2s")
            return response("No action is needed.")

    async def no_wait(_delay):
        pass

    async def no_initialize():
        pass

    brain = BackboardBrain(llm_provider="google", model_name="gemini-3.6-flash")
    brain.client = RetryClient()
    monkeypatch.setattr(brain, "_ensure_initialized", no_initialize)
    monkeypatch.setattr(backboard_client.asyncio, "sleep", no_wait)
    executed = []

    result = asyncio.run(brain.run_tools("state", "prompt", [], lambda *args: executed.append(args), "Auto"))

    assert result == []
    assert executed == []
    assert len(brain.client.requests) == 2
    assert brain.client.requests[1]["thread_id"] == "thread"
    assert BackboardBrain._retry_delay("retryDelay: 2.5s", 0) == 2.5
