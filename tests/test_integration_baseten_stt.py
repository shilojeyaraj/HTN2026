"""Integration test for Baseten STT (voice/stt.py).

Hits the real Baseten Whisper API. Requires BASETEN_API_KEY and
BASETEN_STT_MODEL_ID in .env. The model ID won't be available until you
deploy Whisper at the Baseten booth (see TODO.md).
Run: pytest -m integration -k baseten_stt
"""

import os
import tempfile
import wave

import numpy as np
import pytest

from tests.conftest import has_real_key

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not has_real_key("BASETEN_API_KEY") or not os.environ.get("BASETEN_STT_MODEL_ID"),
        reason="BASETEN_API_KEY or BASETEN_STT_MODEL_ID not set (deploy Whisper at Baseten booth first)",
    ),
]


def _make_test_wav(text_duration_s=1.0) -> str:
    """Generate a short silent WAV file for the API call."""
    sr = 16000
    samples = np.zeros(int(sr * text_duration_s), dtype=np.int16)
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(samples.tobytes())
    return path


def test_baseten_stt_transcribes_audio():
    from voice.stt import transcribe

    wav_path = _make_test_wav()
    try:
        result = transcribe(wav_path)
        assert isinstance(result, str)
        # Silent audio may return empty string, but the API should respond
        # without error. The test verifies the request/response path works.
        print(f"\n  Baseten STT returned: '{result}'")
    finally:
        os.unlink(wav_path)
