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

# TODO: pick the rover's actual voice from the ElevenLabs dashboard and swap this id.
VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
MODEL_ID = "eleven_flash_v2_5"  # ~75ms latency, matters for a live demo narrating decisions


def _play(text: str) -> None:
    audio = _client.text_to_speech.convert(text=text, voice_id=VOICE_ID, model_id=MODEL_ID)
    play(audio)


def speak(text: str) -> None:
    threading.Thread(target=_play, args=(text,), daemon=True).start()
