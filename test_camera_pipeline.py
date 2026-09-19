"""Run with python3 -m unittest test_camera_pipeline (no model download)."""

import io
import json
import socket
import struct
import threading
import unittest

import numpy as np
from PIL import Image

from laptop.server import handle_connection, summarize
from shared.protocol import MAX_FRAME, MAX_RESULT, receive, send


class PipelineTest(unittest.TestCase):
    def test_scores(self):
        depth = np.tile(np.repeat([2, 8, 5], 10), (20, 1))
        result = summarize(depth)
        self.assertEqual(result["preferred_direction"], "left")
        self.assertEqual(result["relative_proximity"], {"left": 0, "center": 1, "right": 0.5})
        self.assertEqual(summarize(np.ones((20, 30)))["status"], "uncertain")
        with self.assertRaises(ValueError):
            summarize(np.full((20, 30), np.nan))

    def test_roundtrip_and_recovery(self):
        displayed = []
        client, server = socket.socketpair()
        client.settimeout(2)
        server.settimeout(2)
        errors = []

        def serve():
            with server:
                try:
                    handle_connection(server, lambda image: np.tile(np.arange(30), (20, 1)), displayed.append)
                except EOFError:
                    pass
                except Exception as exc:
                    errors.append(exc)

        thread = threading.Thread(target=serve)
        thread.start()
        try:
            with client:
                with self.assertLogs(level="ERROR"):
                    send(client, b"bad jpeg", MAX_FRAME)
                    self.assertEqual(json.loads(receive(client, MAX_RESULT))["status"], "error")
                self.assertEqual(displayed, [])
                jpeg = io.BytesIO()
                Image.new("RGB", (64, 48)).save(jpeg, format="JPEG")
                # Send fragmented headers and payload to exercise TCP stream framing.
                payload = jpeg.getvalue()
                packet = struct.pack("!I", len(payload)) + payload
                for start in range(0, len(packet), 3):
                    client.sendall(packet[start:start + 3])
                result = json.loads(receive(client, MAX_RESULT))
                self.assertEqual(result["preferred_direction"], "left")
                self.assertTrue(result["advisory_only"])
                send(client, payload, MAX_FRAME)
                self.assertEqual(json.loads(receive(client, MAX_RESULT))["status"], "ok")
                self.assertEqual(len(displayed), 2)
                for image in displayed:
                    self.assertEqual(image.size, (64, 48))
                    self.assertEqual(image.mode, "RGB")
        finally:
            client.close()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertFalse(errors)

    def test_bad_lengths_and_disconnect(self):
        for length in (0, MAX_FRAME + 1):
            client, server = socket.socketpair()
            with client, server:
                client.sendall(struct.pack("!I", length))
                with self.assertRaises(ValueError):
                    receive(server, MAX_FRAME)
        client, server = socket.socketpair()
        with client, server:
            client.sendall(struct.pack("!I", 10) + b"short")
            client.shutdown(socket.SHUT_WR)
            with self.assertRaises(EOFError):
                receive(server, MAX_FRAME)


if __name__ == "__main__":
    unittest.main()
