"""Run with python3 -m unittest test_camera_pipeline (no model download)."""

import io
import json
import socket
import struct
import subprocess
import sys
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import numpy as np
from PIL import Image

from laptop.server import handle_connection, summarize
from pi.client import mjpeg_frames, stream
from shared.protocol import MAX_FRAME, MAX_RESULT, receive, send


class PipelineTest(unittest.TestCase):
    def test_client_camera_process_roundtrip_and_cleanup(self):
        self.check_camera_roundtrip(lambda image: np.tile(np.arange(30), (20, 1)), "ok")

    def test_preview_only_roundtrip(self):
        self.check_camera_roundtrip(None, "preview")

    def check_camera_roundtrip(self, infer, status):
        jpeg = io.BytesIO()
        Image.new("RGB", (64, 48)).save(jpeg, format="JPEG")
        # Real pipe/process, standing in for CSI hardware. No image files.
        camera = subprocess.Popen([
            sys.executable, "-c",
            "import sys,time; sys.stdout.buffer.write(" + repr(jpeg.getvalue()) +
            "); sys.stdout.buffer.flush(); time.sleep(20)",
        ], stdout=subprocess.PIPE)
        client, server = socket.socketpair()
        client.settimeout(3)
        server.settimeout(3)
        errors = []

        def serve():
            with server:
                try:
                    handle_connection(server, infer)
                except EOFError:
                    pass
                except Exception as exc:
                    errors.append(exc)

        worker = threading.Thread(target=serve)
        worker.start()
        try:
            with client, patch("pi.client.subprocess.Popen", return_value=camera) as launch:
                with patch("builtins.print") as output:
                    stream(client, SimpleNamespace(image=None, once=True, fps=15, quality=70, timeout=3))
                result = json.loads(output.call_args.args[0])
                self.assertEqual(result["frame_id"], 1)
                self.assertEqual(result["status"], status)
                self.assertIn("rpicam-vid", launch.call_args.args[0])
                self.assertIsNotNone(camera.poll(), "camera process leaked")
        finally:
            client.close()
            if camera.poll() is None:
                camera.kill()
            camera.wait()
            camera.stdout.close()
            worker.join(4)
        self.assertFalse(worker.is_alive())
        self.assertFalse(errors)

    def test_mjpeg_framing(self):
        frames = [b"\xff\xd8abc\xff\xd9", b"\xff\xd8def\xff\xd9"]
        stream = b"".join(frames)
        self.assertEqual(list(mjpeg_frames([bytes([byte]) for byte in stream])), frames)
        self.assertEqual(list(mjpeg_frames([stream])), frames)
        with self.assertRaises(EOFError):
            list(mjpeg_frames([frames[0][:-1]]))
        with self.assertRaises(ValueError):
            list(mjpeg_frames([b"\xff\xd8" + b"x" * MAX_FRAME]))

    def test_preview_continues_while_depth_is_busy(self):
        client, server = socket.socketpair()
        client.settimeout(3)
        server.settimeout(3)
        busy = threading.Event()
        release = threading.Event()
        all_displayed = threading.Event()
        displayed = []
        inferred = []
        errors = []

        def infer(image):
            inferred.append(image)
            if len(inferred) == 1:
                busy.set()
                if not release.wait(3):
                    raise TimeoutError("test did not release inference")
            return np.tile(np.arange(30), (20, 1))

        def display(image):
            displayed.append(image)
            if len(displayed) == 10:
                all_displayed.set()

        def serve():
            with server:
                try:
                    handle_connection(server, infer, display)
                except EOFError:
                    pass
                except Exception as exc:
                    errors.append(exc)

        worker = threading.Thread(target=serve)
        worker.start()
        try:
            jpeg = io.BytesIO()
            Image.new("RGB", (64, 48)).save(jpeg, format="JPEG")
            send(client, jpeg.getvalue(), MAX_FRAME)
            self.assertTrue(busy.wait(2))
            for _ in range(9):
                send(client, jpeg.getvalue(), MAX_FRAME)
            self.assertTrue(all_displayed.wait(2), "preview blocked behind depth")
            release.set()
            self.assertEqual(json.loads(receive(client, MAX_RESULT))["frame_id"], 1)
            self.assertEqual(json.loads(receive(client, MAX_RESULT))["frame_id"], 10)
            self.assertEqual(len(inferred), 2, "queued old frames instead of dropping them")
        finally:
            release.set()
            client.close()
            worker.join(4)
        self.assertFalse(worker.is_alive())
        self.assertFalse(errors)

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
