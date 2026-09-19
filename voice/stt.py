"""Push-to-talk voice-in, routed through Backboard's own STT (voice={"stt": ...}) rather
than a direct provider — this is Backboard's slice now that Baseten's role moved to the
fine-tuned vision model (PRIZE_TRACKS.md), and it shares the planner's mission thread so
a spoken command lands in the same history/memory the planner sees.
"""

from brain.backboard_client import brain


def record_while_held(is_held) -> str:
    """Records mic audio while `is_held()` is True, returns a path to the recorded wav file."""
    raise NotImplementedError  # hardware: USB mic capture + push-button trigger


def transcribe(audio_path: str) -> str:
    return brain.transcribe(audio_path)
