"""Static Backboard documents must never hold up planner requests for indexing."""

import asyncio
import logging
from types import SimpleNamespace

from brain.backboard_client import BackboardBrain, ENCOUNTERS


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


def test_static_documents_do_not_wait_for_indexing():
    brain = object.__new__(BackboardBrain)
    brain.client = FakeClient()
    brain.assistant_id = None
    brain._knowledge_uploaded = False
    brain._encounters_loaded = False

    asyncio.run(brain._ensure_initialized())

    assert len(brain.client.uploaded) == 2
    assert len(brain.client.memories) == len(ENCOUNTERS)


def test_backboard_client_closes_once_at_shutdown():
    class ClosingClient:
        closed = 0

        async def aclose(self):
            self.closed += 1

    brain = object.__new__(BackboardBrain)
    brain.client = ClosingClient()

    asyncio.run(brain.aclose())

    assert brain.client is None


def test_failed_planner_response_logs_parsed_payload(caplog):
    class FailedResponse:
        status = "FAILED"

        def model_dump(self, **_kwargs):
            return {"messages": [{"status": "FAILED", "error": "model unavailable"}]}

    with caplog.at_level(logging.ERROR):
        BackboardBrain._log_response("response", FailedResponse(), 0.1)

    assert "parsed response type=FailedResponse" in caplog.text
    assert "model unavailable" in caplog.text
