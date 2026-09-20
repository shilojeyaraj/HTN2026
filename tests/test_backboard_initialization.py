"""Static Backboard documents must never hold up planner requests for indexing."""

import asyncio
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
