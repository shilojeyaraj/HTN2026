"""Push-to-talk voice-in via a Baseten-hosted Whisper model, called directly (CLAUDE.md
section 4) -- this is Baseten's track slice, not routed through Backboard. Baseten's
optional command-parser fine-tune (CLAUDE.md section 13) is a separate, deferred side
quest and doesn't live here.
"""

import os

import requests

PREDICT_URL_TEMPLATE = "https://model-{model_id}.api.baseten.co/environments/production/predict"


def record_while_held(is_held) -> str:
    """Records mic audio while `is_held()` is True, returns a path to the recorded wav file."""
    raise NotImplementedError  # hardware: USB mic capture + push-button trigger


def transcribe(audio_path: str) -> str:
    model_id = os.environ["BASETEN_STT_MODEL_ID"]
    # VERIFY: exact request/response schema once Whisper Large V3 Turbo is deployed --
    # Baseten Truss packaging varies, this multipart-audio shape is a reasonable default,
    # not a confirmed contract (BUILD_PLAN.md).
    with open(audio_path, "rb") as audio_file:
        response = requests.post(
            PREDICT_URL_TEMPLATE.format(model_id=model_id),
            headers={"Authorization": f"Api-Key {os.environ['BASETEN_API_KEY']}"},
            files={"audio": audio_file},
            timeout=15,
        )
    response.raise_for_status()
    return response.json()["text"]
