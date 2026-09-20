"""Offline checks for GPT-4.1 image input and the shared HTTP client lifecycle."""

import base64
import json
from unittest.mock import Mock

import httpx
import pytest

from perception import vision


def vision_response(text):
    return httpx.Response(200, request=httpx.Request("POST", "https://api.openai.com/v1/responses"), json={
        "status": "completed",
        "output": [{"type": "message", "content": [{"type": "output_text", "text": text}]}],
    })


@pytest.fixture(autouse=True)
def reset_vision(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(vision, "MODEL", "gpt-4.1")
    monkeypatch.setattr(vision, "_client", None)
    monkeypatch.setattr(vision, "MIN_INTERVAL_S", 0)
    monkeypatch.setattr(vision, "_next_request_at", 0)
    monkeypatch.setattr(vision, "_rate_limit_attempt", 0)
    monkeypatch.setattr(vision, "_blocked_reason", None)
    yield
    vision.close_vision_client()


def test_describe_scene_sends_jpeg_to_gpt41_and_reuses_client_until_shutdown(monkeypatch):
    requests = []

    def handle(request):
        requests.append(request)
        return vision_response("  Clear floor ahead.  ")

    real_client = httpx.Client
    factory = Mock(side_effect=lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    monkeypatch.setattr(vision.httpx, "Client", factory)

    assert vision.describe_scene(b"first jpeg") == "Clear floor ahead."
    client = vision._client
    assert not client.is_closed
    assert vision.describe_scene(b"next jpeg") == "Clear floor ahead."
    assert not client.is_closed
    factory.assert_called_once()
    assert factory.call_args.kwargs["timeout"] == 30
    for request, jpeg in zip(requests, (b"first jpeg", b"next jpeg")):
        assert str(request.url) == "https://api.openai.com/v1/responses"
        assert request.headers["Authorization"] == "Bearer test-key"
        assert json.loads(request.content) == {
            "model": "gpt-4.1",
            "input": [{"role": "user", "content": [
                {"type": "input_text", "text": vision.PROMPT},
                {"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(jpeg).decode("ascii")},
            ]}],
        }
    vision.close_vision_client()
    assert client.is_closed
    assert vision._client is None
    vision.close_vision_client()  # Duplicate shutdown is safe.


def test_describe_scene_handles_missing_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert vision.describe_scene(b"jpeg") is None
    assert "OPENAI_API_KEY" in vision.vision_unavailable_reason()
    assert vision._client is None


@pytest.mark.parametrize("status,body", [
    (503, {"error": {"message": "temporarily unavailable"}}),
    (200, {"status": "incomplete", "output": vision_response("Partial scene").json()["output"]}),
    (200, {"status": "completed", "output": []}),
    (200, {"status": "completed", "output": [{"type": "message", "content": [{"type": "refusal", "refusal": "Unable to analyze"}]}]}),
])
def test_failed_incomplete_and_empty_responses_do_not_produce_a_scene(status, body, monkeypatch):
    client = httpx.Client(transport=httpx.MockTransport(lambda _: httpx.Response(status, json=body)), base_url="https://api.openai.com/v1/")
    monkeypatch.setattr(vision, "_client", client)
    assert vision.describe_scene(b"jpeg") is None


def test_timeout_is_graceful_and_client_remains_reusable(monkeypatch):
    client = Mock()
    client.post.side_effect = [httpx.ReadTimeout("timed out"), vision_response("Recovered")]
    monkeypatch.setattr(vision, "_client", client)
    assert vision.describe_scene(b"jpeg") is None
    assert vision.describe_scene(b"fresh jpeg") == "Recovered"
    client.close.assert_not_called()


@pytest.mark.parametrize("status", [401, 403])
def test_invalid_credentials_stop_further_requests(status, monkeypatch):
    client = Mock()
    client.post.return_value = httpx.Response(status, request=httpx.Request("POST", "https://api.openai.com/v1/responses"), json={"error": {"message": "Denied"}})
    monkeypatch.setattr(vision, "_client", client)
    assert vision.describe_scene(b"jpeg") is None
    assert vision.describe_scene(b"jpeg") is None
    assert "authorization failed" in vision.vision_unavailable_reason()
    client.post.assert_called_once()
