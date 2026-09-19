"""Inference client for the Baseten-deployed fine-tuned command parser.

Calls the deployed Qwen3-1.7B LoRA model's predict endpoint to parse a natural language
command into a structured verb call. Returns None if the command is unrecognized or
parsing fails, so brain/loop.py can fall through to the Backboard brain for complex
reasoning.

Deploy after training: baseten train checkpoint deploy --job-id <job_id>
Then set BASETEN_PARSER_MODEL_ID in .env.
"""

import json
import os

import requests

PREDICT_URL_TEMPLATE = "https://model-{model_id}.api.baseten.co/environments/production/predict"


def parse(command: str) -> dict | None:
    """Parse a natural language command into a verb call dict, or None if unrecognized."""
    model_id = os.environ.get("BASETEN_PARSER_MODEL_ID")
    if not model_id:
        return None

    try:
        response = requests.post(
            PREDICT_URL_TEMPLATE.format(model_id=model_id),
            headers={"Authorization": f"Api-Key {os.environ['BASETEN_API_KEY']}"},
            json={"prompt": command, "max_new_tokens": 128},
            timeout=10,
        )
        response.raise_for_status()
        text = response.json().get("output") or response.json().get("text") or ""
        text = text.strip()
        # The fine-tuned model outputs a JSON verb call; extract it
        if text.startswith("{"):
            return json.loads(text)
        # Try to find JSON in the response
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
    except (requests.RequestException, json.JSONDecodeError, KeyError):
        return None

    return None
