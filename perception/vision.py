"""Scene understanding through Gemini; Backboard receives only the resulting text."""

import logging
import os

logger = logging.getLogger(__name__)

MODEL = "gemini-2.5-flash"
_client = None

PROMPT = """Describe the scene in 2-3 sentences: notable objects, free space, and any \
hazards. Be concrete about direction. Do not infer measured distances from the image."""


def _get_client(api_key: str):
    global _client
    if _client is None:
        from google import genai

        _client = genai.Client(api_key=api_key)
    return _client


def close_vision_client() -> None:
    """Release the shared Gemini client during application shutdown."""
    global _client
    client, _client = _client, None
    if client is not None:
        try:
            client.close()
        except Exception:
            logger.warning("Gemini vision client did not close cleanly", exc_info=True)


def describe_scene(jpeg_bytes: bytes) -> str | None:
    """Return Gemini's scene description, or None when the frame cannot be analyzed."""
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.warning("Gemini vision unavailable: GEMINI_API_KEY is not set")
        return None

    try:
        from google.genai import types

        response = _get_client(api_key).models.generate_content(
            model=MODEL,
            contents=[
                types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg"),
                PROMPT,
            ],
        )
        return response.text.strip() if response.text else None
    except Exception:
        logger.warning("Gemini vision request failed", exc_info=True)
        return None
