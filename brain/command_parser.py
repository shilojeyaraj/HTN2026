"""Inference client for the Baseten-deployed fine-tuned command parser.

Calls the deployed Qwen3-1.7B LoRA checkpoint served by vLLM on Baseten. The endpoint
is OpenAI-compatible (/v1/chat/completions), served under the model name "checkpoint-105".
Returns None if the command is unrecognized or parsing fails, so brain/loop.py can fall
through to the Backboard brain for complex reasoning.

Deployed via: baseten train checkpoint deploy --config training/deploy_config.py
Then set BASETEN_PARSER_MODEL_ID in .env.
"""

import json
import os

import requests

CHAT_URL_TEMPLATE = "https://model-{model_id}.api.baseten.co/environments/production/v1/chat/completions"
SERVED_MODEL = "checkpoint-105"

SYSTEM = "You parse natural-language rover commands into a single JSON verb call. " \
         "Respond with ONLY the JSON object, no prose. Verbs: forward(distance_m), " \
         "backward(distance_m), turn(degrees), stop(). Example: \"forward 2 meters\" -> " \
         '{"verb": "forward", "args": {"distance_m": 2.0}}'


def parse(command: str) -> dict | None:
    """Parse a natural language command into a verb call dict, or None if unrecognized."""
    model_id = os.environ.get("BASETEN_PARSER_MODEL_ID")
    if not model_id:
        return None

    try:
        response = requests.post(
            CHAT_URL_TEMPLATE.format(model_id=model_id),
            headers={
                "Authorization": f"Api-Key {os.environ['BASETEN_API_KEY']}",
                "Content-Type": "application/json",
            },
            json={
                "model": SERVED_MODEL,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": command},
                ],
                "max_tokens": 128,
                "temperature": 0.0,
            },
            timeout=10,
        )
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"].strip()
        if text.startswith("{"):
            return json.loads(text)
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])
    except (requests.RequestException, json.JSONDecodeError, KeyError, IndexError):
        return None

    return None
