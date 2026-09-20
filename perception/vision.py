"""Scene understanding through Gemini; Backboard receives only the resulting text."""

import logging
import os
import time

from shared.inference import is_daily_quota, is_rate_limited, retry_delay

logger = logging.getLogger(__name__)

MODEL = os.getenv("GEMINI_VISION_MODEL", "gemini-3.6-flash")
FALLBACK_MODEL = os.getenv("GEMINI_VISION_FALLBACK_MODEL", "gemini-3.5-flash-lite")
MIN_INTERVAL_S = float(os.getenv("VISION_MIN_INTERVAL_S", "6"))
_client = None
_active_model = MODEL
_next_request_at = 0.0
_rate_limit_attempt = 0
_blocked_reason = None

PROMPT = """Describe the scene in 2-3 sentences: notable objects, free space, and any \
hazards. Be concrete about direction. Do not infer measured distances from the image."""


def _get_client(api_key: str):
    global _client
    if _client is None:
        from google import genai

        # Handle 429s here so the SDK does not silently sleep/retry five times.
        _client = genai.Client(api_key=api_key, http_options={
            "timeout": 30000, "retry_options": {"attempts": 1},
        })
    return _client


def close_vision_client() -> None:
    """Release the shared Gemini client during application shutdown."""
    global _client, _active_model, _next_request_at, _rate_limit_attempt, _blocked_reason
    client, _client = _client, None
    _active_model, _next_request_at, _rate_limit_attempt, _blocked_reason = MODEL, 0.0, 0, None
    if client is not None:
        try:
            client.close()
        except Exception:
            logger.warning("Gemini vision client did not close cleanly", exc_info=True)


def vision_retry_delay() -> float:
    """Let the outer loop wait before capturing its next live frame."""
    return max(0.0, _next_request_at - time.monotonic())


def vision_unavailable_reason() -> str | None:
    return _blocked_reason


def describe_scene(jpeg_bytes: bytes) -> str | None:
    """Return Gemini's scene description, or None when the frame cannot be analyzed."""
    global _active_model, _next_request_at, _rate_limit_attempt, _blocked_reason
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("Gemini vision unavailable: GEMINI_API_KEY is not set")
        return None
    if _blocked_reason or vision_retry_delay() > 0:
        return None

    while True:
        try:
            from google.genai import types

            logger.info("Gemini vision: sending %d-byte JPEG model=%s", len(jpeg_bytes), _active_model)
            started = time.monotonic()
            _next_request_at = started + MIN_INTERVAL_S
            response = _get_client(api_key).models.generate_content(
                model=_active_model,
                contents=[types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"), PROMPT],
            )
            description = response.text.strip() if response.text else None
            _rate_limit_attempt = 0
            logger.info("Gemini vision: completed in %.2fs", time.monotonic() - started)
            return description
        except Exception as exc:
            if not is_rate_limited(exc):
                logger.warning("Gemini vision request failed: %s", exc)
                return None
            daily = is_daily_quota(exc)
            if daily or _rate_limit_attempt >= 3:
                if FALLBACK_MODEL and _active_model != FALLBACK_MODEL:
                    logger.warning("Gemini vision: %s for %s; switching to %s for this session",
                                   "daily quota exhausted" if daily else "retries exhausted",
                                   _active_model, FALLBACK_MODEL)
                    _active_model, _rate_limit_attempt = FALLBACK_MODEL, 0
                    continue
                if daily:
                    _blocked_reason = (f"Vision daily quota exhausted for {_active_model}; enable Gemini billing "
                                       "or configure GEMINI_VISION_MODEL with available quota. Robot remains stopped.")
                    logger.error(_blocked_reason)
                    return None
            response = getattr(exc, "response", None)
            retry_after = response.headers.get("Retry-After") if response is not None else None
            delay = retry_delay(exc, _rate_limit_attempt, retry_after)
            _rate_limit_attempt += 1
            _next_request_at = time.monotonic() + delay
            logger.warning("Gemini vision: rate limited; retry with a fresh frame in %.1fs; no movement", delay)
            return None
