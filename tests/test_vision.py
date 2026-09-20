"""Unit tests for the direct Gemini vision boundary."""

import sys
from types import ModuleType, SimpleNamespace

from perception import vision


def test_describe_scene_sends_jpeg_to_gemini(monkeypatch):
    calls = {"created": 0, "closed": 0}

    class FakePart:
        @staticmethod
        def from_bytes(**kwargs):
            return kwargs

    class FakeClient:
        def __init__(self, **kwargs):
            calls["created"] += 1
            calls["api_key"] = kwargs["api_key"]
            self.models = SimpleNamespace(generate_content=self.generate_content)

        def generate_content(self, **kwargs):
            calls.update(kwargs)
            return SimpleNamespace(text="  Clear floor ahead.  ")

        def close(self):
            calls["closed"] += 1

    types_module = ModuleType("google.genai.types")
    types_module.Part = FakePart
    genai_module = ModuleType("google.genai")
    genai_module.Client = FakeClient
    genai_module.types = types_module
    google_module = ModuleType("google")
    google_module.genai = genai_module
    monkeypatch.setitem(sys.modules, "google", google_module)
    monkeypatch.setitem(sys.modules, "google.genai", genai_module)
    monkeypatch.setitem(sys.modules, "google.genai.types", types_module)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(vision, "_client", None)

    assert vision.describe_scene(b"jpeg") == "Clear floor ahead."
    assert vision.describe_scene(b"jpeg") == "Clear floor ahead."
    vision.close_vision_client()
    assert calls == {
        "created": 1,
        "closed": 1,
        "api_key": "test-key",
        "model": "gemini-3.6-flash",
        "contents": [{"data": b"jpeg", "mime_type": "image/jpeg"}, vision.PROMPT],
    }


def test_describe_scene_handles_missing_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(vision, "_client", None)

    assert vision.describe_scene(b"jpeg") is None
