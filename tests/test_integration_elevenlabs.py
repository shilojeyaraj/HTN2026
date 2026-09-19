"""Integration test for ElevenLabs TTS (voice/tts.py).

Hits the real ElevenLabs API. Requires ELEVENLABS_API_KEY and VOICE_ID in .env.
Run: pytest -m integration -k elevenlabs
"""

import os
import tempfile
import wave

import pytest

from tests.conftest import has_real_key

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not has_real_key("ELEVENLABS_API_KEY", "VOICE_ID"),
        reason="ELEVENLABS_API_KEY or VOICE_ID not set in .env",
    ),
]


def test_elevenlabs_tts_generates_audio():
    """Verify that ElevenLabs returns playable audio bytes for a short phrase."""
    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
    audio = client.text_to_speech.convert(
        text="Rescue rover online. All systems nominal.",
        voice_id=os.environ["VOICE_ID"],
        model_id="eleven_flash_v2_5",
    )
    if isinstance(audio, (bytes, bytearray)):
        audio_bytes = bytes(audio)
    else:
        audio_bytes = b"".join(audio)
    assert len(audio_bytes) > 1000, f"Audio too short ({len(audio_bytes)} bytes), expected a real audio stream"
    print(f"\n  ElevenLabs returned {len(audio_bytes)} bytes of audio")


def test_tts_speak_does_not_block():
    """Verify that speak() fires async and returns immediately (CLAUDE.md section 10)."""
    from voice.tts import speak

    import time
    start = time.monotonic()
    speak("Test message.")
    elapsed = time.monotonic() - start
    assert elapsed < 1.0, f"speak() blocked for {elapsed:.2f}s, should be async"
    print(f"\n  speak() returned in {elapsed:.4f}s (async, non-blocking)")
