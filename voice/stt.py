"""Push-to-talk voice-in via a Baseten-hosted Whisper model, called directly (CLAUDE.md
section 4) -- this is Baseten's track slice, not routed through Backboard. Baseten's
optional command-parser fine-tune (CLAUDE.md section 13) is a separate, deferred side
quest and doesn't live here.
"""

import base64
import os
import tempfile
import wave

import numpy as np
import requests
import sounddevice as sd

PREDICT_URL_TEMPLATE = "https://model-{model_id}.api.baseten.co/environments/production/predict"
SAMPLE_RATE = 16000
POLL_CHUNK_FRAMES = 1024


def record_while_held(is_held) -> str:
    """Records mic audio while `is_held()` is True, returns a path to the recorded wav file."""
    frames = []
    with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16") as stream:
        while is_held():
            chunk, _ = stream.read(POLL_CHUNK_FRAMES)
            frames.append(chunk.copy())

    audio = np.concatenate(frames, axis=0) if frames else np.zeros((0, 1), dtype="int16")

    fd, path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # int16
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(audio.tobytes())
    return path


def transcribe(audio_path: str) -> str:
    model_id = os.environ["BASETEN_STT_MODEL_ID"]
    with open(audio_path, "rb") as audio_file:
        audio_b64 = base64.b64encode(audio_file.read()).decode("utf-8")
    response = requests.post(
        PREDICT_URL_TEMPLATE.format(model_id=model_id),
        headers={"Authorization": f"Api-Key {os.environ['BASETEN_API_KEY']}"},
        json={
            "whisper_input": {
                "audio": {"audio_b64": audio_b64},
                "whisper_params": {"audio_language": "en"},
            }
        },
        timeout=15,
    )
    response.raise_for_status()
    segments = response.json()["segments"]
    return " ".join(seg["text"] for seg in segments).strip()
