"""Recording round-trip and orderly receiver shutdown checks."""

import io
import json
from pathlib import Path
import socket
import tempfile
import threading
import unittest

import av
from PIL import Image

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
                        handle_connection(server, None, recording=recorder, shutdown=shutdown)
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
                    pcm = b"\x00\x01" * 320
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
            with av.open(recorder.path) as container:
                self.assertEqual([s.type for s in container.streams], ["audio", "video"])
                frames = list(container.decode())
            self.assertEqual(sum(isinstance(f, av.VideoFrame) for f in frames), 2)
            audio = [f for f in frames if isinstance(f, av.AudioFrame)]
            self.assertEqual(sum(f.samples for f in audio), 320)
            self.assertEqual(audio[0].to_ndarray().tobytes(), pcm)

    def test_audio_only_and_unique_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            for _ in range(2):
                recorder = Recording(directory)
                recorder.audio(bytes(640))
                recorder.close()
                with av.open(recorder.path) as container:
                    self.assertEqual(sum(frame.samples for frame in container.decode(audio=0)), 320)
            self.assertEqual(len(list(Path(directory).glob("*.mkv"))), 2)


if __name__ == "__main__":
    unittest.main()
