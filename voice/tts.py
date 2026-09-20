"""ElevenLabs TTS playback, called directly. Reverted from Backboard-routed TTS for
testability -- Backboard's BYOK dashboard flow for connecting our own ElevenLabs key is
unverified/undocumented (BUILD_PLAN.md), while this direct path is proven and testable
right now. Always fired async so it never blocks the control loop.
"""

import os
import threading

from elevenlabs.client import ElevenLabs
from elevenlabs.play import play  # shells out to mpv/ffplay; `sudo apt install mpv` on the Pi

_client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])

VOICE_ID = os.environ["VOICE_ID"]
VICTIM_VOICE_ID = os.environ.get("VICTIM_VOICE_ID", VOICE_ID)
MODEL_ID = "eleven_flash_v2_5"  # ~75ms latency, matters for a live demo narrating decisions


def _play(text: str, voice_id: str = VOICE_ID) -> None:
    audio = _client.text_to_speech.convert(text=text, voice_id=voice_id, model_id=MODEL_ID)
    play(audio)


def speak(text: str) -> None:
    threading.Thread(target=_play, args=(text,), daemon=True).start()


def speak_as_victim(text: str) -> None:
    """Speak as the victim using a different voice."""
    threading.Thread(target=_play, args=(text, VICTIM_VOICE_ID), daemon=True).start()
