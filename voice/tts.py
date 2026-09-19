"""Text-to-speech, routed through Backboard using ElevenLabs (BYOK'd within Backboard --
team decision, PRIZE_TRACKS.md) rather than a direct ElevenLabs SDK call. Always fired
async so it never blocks the control loop.
"""

import subprocess
import tempfile
import threading

import requests

from brain.backboard_client import brain


def _play(text: str) -> None:
    audio_url = brain.speak_to_url(text)
    response = requests.get(audio_url, timeout=10)
    response.raise_for_status()
    with tempfile.NamedTemporaryFile(suffix=".mp3") as f:
        f.write(response.content)
        f.flush()
        subprocess.run(["mpv", "--no-video", f.name], check=False)  # `sudo apt install mpv` on the Pi


def speak(text: str) -> None:
    threading.Thread(target=_play, args=(text,), daemon=True).start()
