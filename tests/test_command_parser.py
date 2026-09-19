"""Unit tests for the command parser (brain/command_parser.py).

Pure logic, no network. Mocks the HTTP call to verify JSON extraction logic
from various response formats.
"""

import json
from unittest.mock import patch, MagicMock

from brain import command_parser


def _mock_chat_response(content: str):
    """Mock an OpenAI-compatible /v1/chat/completions response."""
    mock = MagicMock()
    mock.json.return_value = {"choices": [{"message": {"content": content}}]}
    mock.raise_for_status.return_value = None
    return mock


_ENV = {
    "BASETEN_PARSER_MODEL_ID": "test-model",
    "BASETEN_API_KEY": "test-key",
}


class TestParseNoModel:
    def test_returns_none_when_model_id_unset(self):
        with patch.dict("os.environ", {"BASETEN_PARSER_MODEL_ID": ""}, clear=False):
            result = command_parser.parse("forward 2 meters")
            assert result is None


class TestParseJsonExtraction:
    def test_parses_clean_json_output(self):
        expected = {"verb": "forward", "args": {"distance_m": 2.0}}
        with patch.dict("os.environ", _ENV, clear=False), patch("requests.post") as mock_post:
            mock_post.return_value = _mock_chat_response(json.dumps(expected))
            result = command_parser.parse("forward 2 meters")
            assert result == expected

    def test_parses_json_embedded_in_text(self):
        expected = {"verb": "turn", "args": {"degrees": -90}}
        with patch.dict("os.environ", _ENV, clear=False), patch("requests.post") as mock_post:
            mock_post.return_value = _mock_chat_response(f"Sure! {json.dumps(expected)} done.")
            result = command_parser.parse("turn right 90 degrees")
            assert result == expected

    def test_parses_json_from_output_field(self):
        expected = {"verb": "stop", "args": {}}
        with patch.dict("os.environ", _ENV, clear=False), patch("requests.post") as mock_post:
            mock_post.return_value = _mock_chat_response(json.dumps(expected))
            result = command_parser.parse("stop")
            assert result == expected

    def test_returns_none_on_invalid_json(self):
        with patch.dict("os.environ", _ENV, clear=False), patch("requests.post") as mock_post:
            mock_post.return_value = _mock_chat_response("not json at all")
            result = command_parser.parse("do something weird")
            assert result is None

    def test_returns_none_on_request_exception(self):
        import requests
        with patch.dict("os.environ", _ENV, clear=False), patch("requests.post") as mock_post:
            mock_post.side_effect = requests.RequestException("network error")
            result = command_parser.parse("forward 2 meters")
            assert result is None

    def test_returns_none_on_no_json_found(self):
        with patch.dict("os.environ", _ENV, clear=False), patch("requests.post") as mock_post:
            mock_post.return_value = _mock_chat_response("no braces here")
            result = command_parser.parse("hello world")
            assert result is None
