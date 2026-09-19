"""Scene understanding, routed through Backboard using Gemini (BYOK'd within Backboard --
team decision, PRIZE_TRACKS.md) rather than a direct Gemini SDK call.
"""

import tempfile

from brain.backboard_client import brain
from brain.state import Detection

PROMPT = """Describe the scene in 2-3 sentences: notable objects, free space, and any \
hazards. Be concrete about direction and distance."""


def describe_scene(jpeg_bytes: bytes, detections: list[Detection]) -> str:
    with tempfile.NamedTemporaryFile(suffix=".jpg") as f:
        f.write(jpeg_bytes)
        f.flush()
        return brain.describe(content=f"{PROMPT}\nDetections: {detections}", image_path=f.name)
