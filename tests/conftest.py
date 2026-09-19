"""Shared pytest fixtures.

Loads .env for integration tests, then fills in dummy placeholders for any
missing key so modules that read os.environ[...] at import time (voice/tts.py,
brain/backboard_client.py) don't crash unit tests that never touch the network.

Integration tests (marked @pytest.mark.integration) hit real APIs and need the
real keys in .env. They're skipped automatically when a required key is
missing or still a dummy. Run them explicitly with:
    pytest -m integration
Unit tests (the default) never make network calls.
"""

import os

from dotenv import load_dotenv

load_dotenv()

_DUMMY_DEFAULTS = {
    "BACKBOARD_API_KEY": "dummy-backboard-key",
    "ELEVENLABS_API_KEY": "dummy-elevenlabs-key",
    "VOICE_ID": "dummy-voice-id",
    "BASETEN_API_KEY": "dummy-baseten-key",
}
for key, value in _DUMMY_DEFAULTS.items():
    os.environ.setdefault(key, value)


def pytest_configure(config):
    config.addinivalue_line("markers", "integration: hits a real cloud API, needs real keys in .env")


def has_real_key(*names: str) -> bool:
    """True if every named env var is set to something other than our dummy default."""
    for name in names:
        value = os.environ.get(name)
        if not value or value == _DUMMY_DEFAULTS.get(name):
            return False
    return True
