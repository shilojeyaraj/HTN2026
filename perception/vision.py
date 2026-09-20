"""Scene understanding, routed through Backboard using Gemini (BYOK'd within Backboard --
team decision, PRIZE_TRACKS.md) rather than a direct Gemini SDK call.
"""

import tempfile

from brain.backboard_client import brain

PROMPT = """Describe the scene in 2-3 sentences: notable objects, free space, and any \
hazards. Be concrete about direction. Do not infer measured distances from the image."""


def describe_scene(jpeg_bytes: bytes) -> str:
    with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
        f.write(jpeg_bytes)
        f.flush()
        return brain.describe(content=PROMPT, image_path=f.name)
