"""A model fine-tuned on real-world footage the rover captures, deployed on Baseten.

This is the Baseten track's slice (PRIZE_TRACKS.md): train, not just infer. The exact
task (classification vs. detection, which classes) depends on what footage is practical
to capture and label at the event, so this stays a thin, generic wrapper until the model
exists. It hits the model's own dedicated predict endpoint, not the shared
`inference.baseten.co/v1` LLM gateway used in brain/llm_client.py.
"""

import base64
import os

import requests

PREDICT_URL_TEMPLATE = "https://model-{model_id}.api.baseten.co/environments/production/predict"


def classify_frame(jpeg_bytes: bytes) -> dict:
    model_id = os.environ["BASETEN_VISION_MODEL_ID"]
    # VERIFY: exact input key/shape once the model is deployed — Baseten Truss packaging
    # varies, this base64-JSON shape is a reasonable default, not a confirmed contract.
    response = requests.post(
        PREDICT_URL_TEMPLATE.format(model_id=model_id),
        headers={"Authorization": f"Api-Key {os.environ['BASETEN_API_KEY']}"},
        json={"image": base64.b64encode(jpeg_bytes).decode()},
        timeout=5,
    )
    response.raise_for_status()
    return response.json()
