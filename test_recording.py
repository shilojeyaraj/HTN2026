"""Recording round-trip and orderly receiver shutdown checks."""

import io
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest
import wave

import av
from PIL import Image

from laptop.audio import audio_transcription
from laptop.recording import Recording
from laptop.server import handle_connection
from shared.protocol import AUDIO_PREFIX, MAX_FRAME, MAX_RESULT, receive, send


class RecordingTest(unittest.TestCase):
    def test_recording_finalizes_on_shutdown(self):
        with tempfile.TemporaryDirectory() as directory:
            recorder = Recording(directory)
            client, server = socket.socketpair()
            client.settimeout(2)
            server.settimeout(2)
            shutdown = threading.Event()
            errors = []

            def serve():
                with server:
                    try:
                        with audio_transcription(lambda pcm: "Final words.", recorder.transcript) as audio:
                            handle_connection(server, None, receive_audio=audio,
                                              recording=recorder, shutdown=shutdown)
                    except EOFError:
                        pass
                    except Exception as exc:
                        errors.append(exc)
                    finally:
                        recorder.close()

            worker = threading.Thread(target=serve)
            worker.start()
            try:
                with client:
                    pcm = b"\x00\x20" * 320
                    for _ in range(15):
                        send(client, AUDIO_PREFIX + pcm, MAX_FRAME)  # Audio before first video.
                    jpeg = io.BytesIO()
                    Image.new("RGB", (64, 48), "red").save(jpeg, format="JPEG")
                    for _ in range(2):
                        send(client, jpeg.getvalue(), MAX_FRAME)
                        self.assertEqual(json.loads(receive(client, MAX_RESULT))["status"], "preview")
                    shutdown.set()  # Close the server while the client is still connected.
                    worker.join(3)
                    self.assertFalse(worker.is_alive())
            finally:
                shutdown.set()
                worker.join(3)
            self.assertFalse(worker.is_alive())
            self.assertFalse(errors)
            with av.open(recorder.path / "video.mp4") as container:
                self.assertEqual([s.type for s in container.streams], ["video"])
                self.assertEqual(container.streams.video[0].codec_context.name, "h264")
                self.assertEqual(len(list(container.decode(video=0))), 2)
            with wave.open(str(recorder.path / "audio.wav")) as audio:
                self.assertEqual(audio.getframerate(), 16000)
                self.assertEqual(audio.getnchannels(), 1)
                self.assertEqual(audio.getsampwidth(), 2)
                self.assertEqual(audio.readframes(4800), pcm * 15)
            self.assertEqual((recorder.path / "transcript.txt").read_text(), "Final words.\n")

    def test_audio_only_and_unique_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            for _ in range(2):
                recorder = Recording(directory)
                recorder.audio(bytes(640))
                recorder.transcript({"text": "provisional", "final": False})
                recorder.transcript({"text": "Hello there.", "final": True})
                recorder.close()
                with wave.open(str(recorder.path / "audio.wav")) as audio:
                    self.assertEqual(audio.getnframes(), 320)
                self.assertEqual((recorder.path / "transcript.txt").read_text(), "Hello there.\n")
            self.assertEqual(len(list(Path(directory).iterdir())), 2)


if __name__ == "__main__":
    unittest.main()
