"""GPT-4.1 scene understanding; Backboard receives only the resulting text."""

import base64
import logging
import os
import time

import httpx

from shared.inference import is_daily_quota, is_rate_limited, retry_delay

logger = logging.getLogger(__name__)

MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-4.1")
MIN_INTERVAL_S = float(os.getenv("VISION_MIN_INTERVAL_S", "6"))
_client = None
_next_request_at = 0.0
_rate_limit_attempt = 0
_blocked_reason = None

PROMPT = """Describe the scene in 2-3 sentences: notable objects, free space, and any \
hazards. Be concrete about direction. Do not infer measured distances from the image."""


def _get_client(api_key: str):
    global _client
    if _client is None:
        # Reuse the HTTP connection; retries/cooldown remain owned by the robot loop.
        _client = httpx.Client(
            base_url="https://api.openai.com/v1/",
            headers={"Authorization": f"Bearer {api_key}"}, timeout=30,
        )
    return _client


def close_vision_client() -> None:
    """Release the shared OpenAI HTTP client during application shutdown."""
    global _client, _next_request_at, _rate_limit_attempt, _blocked_reason
    client, _client = _client, None
    _next_request_at, _rate_limit_attempt, _blocked_reason = 0.0, 0, None
    if client is not None:
        try:
            client.close()
        except Exception:
            logger.warning("OpenAI vision client did not close cleanly", exc_info=True)


def vision_retry_delay() -> float:
    """Let the outer loop wait before capturing its next live frame."""
    return max(0.0, _next_request_at - time.monotonic())


def vision_unavailable_reason() -> str | None:
    return _blocked_reason


def describe_scene(jpeg_bytes: bytes) -> str | None:
    """Return GPT-4.1's scene description, or None when the frame cannot be analyzed."""
    global _next_request_at, _rate_limit_attempt, _blocked_reason
    if _blocked_reason or vision_retry_delay() > 0:
        return None
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        _blocked_reason = "OpenAI vision unavailable: set OPENAI_API_KEY in .env. Robot remains stopped."
        logger.error(_blocked_reason)
        return None

    try:
        logger.info("OpenAI vision: sending %d-byte JPEG model=%s", len(jpeg_bytes), MODEL)
        started = time.monotonic()
        _next_request_at = started + MIN_INTERVAL_S
        response = _get_client(api_key).post("responses", json={
            "model": MODEL,
            "input": [{"role": "user", "content": [
                {"type": "input_text", "text": PROMPT},
                {"type": "input_image", "image_url": "data:image/jpeg;base64," + base64.b64encode(jpeg_bytes).decode("ascii")},
            ]}],
        })
        response.raise_for_status()
        body = response.json()
        if body.get("status") != "completed":
            logger.warning("OpenAI vision returned status=%r; discarding incomplete scene", body.get("status"))
            return None
        description = "\n".join(
            part["text"] for item in body.get("output", []) if item.get("type") == "message"
            for part in item.get("content", []) if part.get("type") == "output_text"
        ).strip()
        _rate_limit_attempt = 0
        logger.info("OpenAI vision: completed in %.2fs", time.monotonic() - started)
        return description or None
    except Exception as exc:
        response = getattr(exc, "response", None)
        # HTTP exceptions omit the JSON error code (e.g. insufficient_quota).
        # Inspect the body for classification without logging credentials or payloads.
        error = f"{exc} {response.text}" if response is not None else str(exc)
        if not is_rate_limited(error):
            logger.warning("OpenAI vision request failed: %s", exc)
            if response is not None and response.status_code in {401, 403}:
                _blocked_reason = "OpenAI vision authorization failed; check OPENAI_API_KEY and model access. Robot remains stopped."
                logger.error(_blocked_reason)
            return None
        if is_daily_quota(error):
            _blocked_reason = (f"Vision quota exhausted for {MODEL}; check OpenAI billing/quota. Robot remains stopped.")
            logger.error(_blocked_reason)
            return None
        retry_after = response.headers.get("Retry-After") if response is not None else None
        delay = retry_delay(error, _rate_limit_attempt, retry_after)
        _rate_limit_attempt += 1
        _next_request_at = time.monotonic() + delay
        logger.warning("OpenAI vision: rate limited; retry with a fresh frame in %.1fs; no movement", delay)
        return None
