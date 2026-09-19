"""Unit tests for the STT module (voice/stt.py).

Pure logic, no network. Mocks the HTTP call to verify the Baseten Whisper
API request format (JSON + base64 audio) and response parsing
(segments[].text joined).
"""

import base64
import json
from unittest.mock import patch, mock_open, MagicMock

from voice import stt


class TestTranscribeRequestFormat:
    def test_sends_json_with_base64_audio(self):
        fake_audio = b"fake-audio-bytes"
        expected_b64 = base64.b64encode(fake_audio).decode("utf-8")

        mock_response = MagicMock()
        mock_response.json.return_value = {"segments": [{"text": "hello world"}]}
        mock_response.raise_for_status.return_value = None

        with patch.dict("os.environ", {
            "BASETEN_STT_MODEL_ID": "test-model",
            "BASETEN_API_KEY": "test-key",
        }), patch("builtins.open", mock_open(read_data=fake_audio)), \
             patch("requests.post", return_value=mock_response) as mock_post:

            result = stt.transcribe("/fake/path.wav")
            assert result == "hello world"

            _, kwargs = mock_post.call_args
            assert kwargs["headers"]["Authorization"] == "Api-Key test-key"
            body = kwargs["json"]
            assert body["whisper_input"]["audio"]["audio_b64"] == expected_b64
            assert body["whisper_input"]["whisper_params"]["audio_language"] == "en"

    def test_joins_multiple_segments(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "segments": [
                {"text": "forward"},
                {"text": "two"},
                {"text": "meters"},
            ]
        }
        mock_response.raise_for_status.return_value = None

        with patch.dict("os.environ", {
            "BASETEN_STT_MODEL_ID": "test-model",
            "BASETEN_API_KEY": "test-key",
        }), patch("builtins.open", mock_open(read_data=b"audio")), \
             patch("requests.post", return_value=mock_response):
            result = stt.transcribe("/fake/path.wav")
            assert result == "forward two meters"

    def test_returns_empty_string_for_no_segments(self):
        mock_response = MagicMock()
        mock_response.json.return_value = {"segments": []}
        mock_response.raise_for_status.return_value = None

        with patch.dict("os.environ", {
            "BASETEN_STT_MODEL_ID": "test-model",
            "BASETEN_API_KEY": "test-key",
        }), patch("builtins.open", mock_open(read_data=b"audio")), \
             patch("requests.post", return_value=mock_response):
            result = stt.transcribe("/fake/path.wav")
            assert result == ""
