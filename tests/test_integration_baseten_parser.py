"""Integration test for the Baseten command parser (brain/command_parser.py).

Hits the real Baseten fine-tuned model API. Requires BASETEN_API_KEY and
BASETEN_PARSER_MODEL_ID in .env. The model ID won't be available until you
train and deploy at the Baseten booth (see TODO.md).
Run: pytest -m integration -k baseten_parser
"""

import os
import pytest

from tests.conftest import has_real_key

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not has_real_key("BASETEN_API_KEY") or not os.environ.get("BASETEN_PARSER_MODEL_ID"),
        reason="BASETEN_API_KEY or BASETEN_PARSER_MODEL_ID not set (train + deploy at Baseten booth first)",
    ),
]


def test_parser_parses_forward_command():
    from brain.command_parser import parse

    result = parse("forward 2 meters")
    assert result is not None, "Parser returned None for a valid command"
    assert result["verb"] == "forward"
    assert "distance_m" in result["args"]
    print(f"\n  Parser result: {result}")


def test_parser_parses_turn_command():
    from brain.command_parser import parse

    result = parse("turn left 90 degrees")
    assert result is not None, "Parser returned None for a valid command"
    assert result["verb"] == "turn"
    assert "degrees" in result["args"]
    print(f"\n  Parser result: {result}")


def test_parser_parses_stop_command():
    from brain.command_parser import parse

    result = parse("stop")
    assert result is not None, "Parser returned None for a valid command"
    assert result["verb"] == "stop"
    print(f"\n  Parser result: {result}")
