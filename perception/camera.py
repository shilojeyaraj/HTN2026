"""Camera bridge: CSI capture on Pi + monocular depth from laptop over TCP.

Replaces the OAK-D/DepthAI stubs. Captures JPEG frames from the Pi's CSI camera
via rpicam-vid, sends them to the laptop depth server (laptop/server.py), and
receives relative depth results back. Converts proximity scores into Detection
objects for the reflex loop and safety gate.

The laptop runs Depth-Anything-V2-Small and returns:
  - relative_proximity: {left, center, right} scores (0-1, higher = nearer)
  - preferred_direction: most open path
  - advisory_only: true (monocular depth is relative, not absolute meters)

We convert proximity to pseudo-detections:
  - distance_m = 1.0 - proximity_score  (monotonic, not true meters)
  - bearing_deg: left=-30, center=0, right=+30
  - label: "obstacle"

Environment variables:
  DEPTH_SERVER_HOST  — laptop IP on the hotspot (default: 127.0.0.1 for testing)
  DEPTH_SERVER_PORT  — TCP port (default: 8765, matches laptop/server.py)
  CSI_FPS           — capture framerate (default: 15)
  CSI_QUALITY       — JPEG quality 1-100 (default: 70)
  CSI_WIDTH         — frame width (default: 640)
  CSI_HEIGHT        — frame height (default: 480)
"""

import json
import logging
import os
import shutil
import socket
import struct
import subprocess
import threading
import time
from collections import deque

from brain.state import Detection
# from perception import ultrasonic  # commented out — teammate is wiring HC-SR04

logger = logging.getLogger(__name__)

DEPTH_HOST = os.environ.get("DEPTH_SERVER_HOST", "127.0.0.1")
DEPTH_PORT = int(os.environ.get("DEPTH_SERVER_PORT", "8765"))
CSI_FPS = int(os.environ.get("CSI_FPS", "15"))
CSI_QUALITY = int(os.environ.get("CSI_QUALITY", "70"))
CSI_WIDTH = int(os.environ.get("CSI_WIDTH", "640"))
CSI_HEIGHT = int(os.environ.get("CSI_HEIGHT", "480"))

REGION_BEARINGS = {"left": -30.0, "center": 0.0, "right": 30.0}
OBSTACLE_THRESHOLD = 0.5
DEPTH_STALENESS_S = 2.0

MAX_FRAME = 2 * 1024 * 1024
MAX_RESULT = 8192


def _recv_exact(sock, size):
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            raise EOFError("connection closed")
        data.extend(chunk)
    return bytes(data)


def _receive(sock, limit):
    size = struct.unpack("!I", _recv_exact(sock, 4))[0]
    if not 0 < size <= limit:
        raise ValueError(f"invalid message length: {size}")
    return _recv_exact(sock, size)


def _send(sock, payload, limit):
    if not 0 < len(payload) <= limit:
        raise ValueError("message too large or empty")
    sock.sendall(struct.pack("!I", len(payload)) + payload)


def _mjpeg_frames(chunks):
    """Split rpicam's MJPEG stream into individual JPEG frames."""
    data = bytearray()
    for chunk in chunks:
        data.extend(chunk)
        while True:
            start = data.find(b"\xff\xd8")
            if start < 0:
                if len(data) > MAX_FRAME:
                    raise ValueError("MJPEG frame start missing")
                break
            del data[:start]
            end = data.find(b"\xff\xd9", 2)
            if end < 0:
                if len(data) > MAX_FRAME:
                    raise ValueError("MJPEG frame exceeds size limit")
                break
            size = end + 2
            if size > MAX_FRAME:
                raise ValueError("MJPEG frame exceeds size limit")
            yield bytes(data[:size])
            del data[:size]
    if data:
        raise EOFError("truncated MJPEG stream")


def _proximity_to_detections(depth_result: dict) -> list[Detection]:
    """Convert relative proximity scores to pseudo-Detection objects."""
    proximity = depth_result.get("relative_proximity")
    if not proximity or depth_result.get("status") != "ok":
        return []

    detections = []
    for region, bearing in REGION_BEARINGS.items():
        score = proximity.get(region)
        if score is not None and score > OBSTACLE_THRESHOLD:
            distance_m = round(1.0 - score, 2)
            detections.append(Detection(
                label="obstacle",
                bbox=(0.0, 0.0, 0.0, 0.0),
                distance_m=distance_m,
                bearing_deg=bearing,
            ))
    return detections


class CameraBridge:
    """Background thread: captures CSI frames, sends to laptop depth server,
    stores latest JPEG + depth result in thread-safe buffers."""

    def __init__(self, host=DEPTH_HOST, port=DEPTH_PORT):
        self.host = host
        self.port = port
        self._jpeg_lock = threading.Lock()
        self._latest_jpeg: bytes = b""
        self._depth_lock = threading.Lock()
        self._latest_depth: dict | None = None
        self._depth_time: float = 0.0
        self._thread: threading.Thread | None = None
        self._running = threading.Event()

    def start(self):
        if self._thread is not None:
            return
        if not shutil.which("rpicam-vid"):
            logger.warning("rpicam-vid not found — camera bridge will return empty data")
            return
        self._running.set()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._running.clear()
        if self._thread:
            self._thread.join(timeout=2)

    def _run(self):
        backoff = 1.0
        while self._running.is_set():
            try:
                self._connect_and_stream()
                backoff = 1.0
            except Exception:
                logger.warning("depth bridge disconnected, retrying in %.0fs", backoff, exc_info=True)
                time.sleep(backoff)
                backoff = min(backoff * 2, 30)

    def _connect_and_stream(self):
        camera = subprocess.Popen(
            [
                "rpicam-vid", "--nopreview", "--timeout", "0",
                "--codec", "mjpeg", "--width", str(CSI_WIDTH),
                "--height", str(CSI_HEIGHT), "--framerate", str(CSI_FPS),
                "--quality", str(CSI_QUALITY), "--flush", "--output", "-",
            ],
            stdout=subprocess.PIPE,
        )

        pending = deque(maxlen=1)
        condition = threading.Condition()
        stopped = threading.Event()
        errors: list = []

        def fail(exc):
            errors.append(exc)
            stopped.set()
            with condition:
                condition.notify_all()

        def capture():
            import selectors
            try:
                def chunk_gen():
                    with selectors.DefaultSelector() as selector:
                        selector.register(camera.stdout, selectors.EVENT_READ)
                        while not stopped.is_set():
                            if not selector.select(5):
                                raise TimeoutError("camera stopped producing frames")
                            chunk = camera.stdout.read1(65536)
                            if not chunk:
                                return
                            yield chunk

                for jpeg in _mjpeg_frames(chunk_gen()):
                    with condition:
                        pending.append(jpeg)
                        condition.notify()
                    with self._jpeg_lock:
                        self._latest_jpeg = jpeg
            except (OSError, EOFError, ValueError) as exc:
                fail(exc)

        def transmit():
            try:
                while not stopped.is_set():
                    with condition:
                        condition.wait_for(lambda: pending or stopped.is_set())
                        if stopped.is_set():
                            return
                        jpeg = pending.pop()
                    _send(sock, jpeg, MAX_FRAME)
            except (OSError, ValueError) as exc:
                fail(exc)

        with socket.create_connection((self.host, self.port), timeout=10) as sock:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)

            workers = [
                threading.Thread(target=capture, daemon=True),
                threading.Thread(target=transmit, daemon=True),
            ]
            for w in workers:
                w.start()

            try:
                while not stopped.is_set():
                    result = json.loads(_receive(sock, MAX_RESULT))
                    if isinstance(result, dict):
                        with self._depth_lock:
                            self._latest_depth = result
                            self._depth_time = time.monotonic()
            except (OSError, EOFError):
                if errors:
                    raise errors[0]
            finally:
                stopped.set()
                with condition:
                    condition.notify_all()
                camera.terminate()
                try:
                    camera.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    camera.kill()
                    camera.wait()
                for w in workers:
                    w.join()

    def get_latest_frame(self) -> tuple[bytes, list[Detection]]:
        with self._jpeg_lock:
            jpeg = self._latest_jpeg
        return jpeg, get_latest_detections()

    def _get_depth_if_fresh(self) -> list[Detection] | None:
        """Returns None when depth is stale/unavailable, [] when fresh-clear,
        list[Detection] when fresh with obstacles."""
        with self._depth_lock:
            depth = self._latest_depth
            age = time.monotonic() - self._depth_time if self._depth_time else float("inf")
        if depth is None or age > DEPTH_STALENESS_S:
            return None
        return _proximity_to_detections(depth)


_bridge: CameraBridge | None = None


def _get_bridge() -> CameraBridge:
    global _bridge
    if _bridge is None:
        _bridge = CameraBridge()
        _bridge.start()
    return _bridge


def get_latest_frame() -> tuple[bytes, list[Detection]]:
    return _get_bridge().get_latest_frame()


def get_latest_detections() -> list[Detection]:
    """Return depth detections. Fail closed when depth is unavailable.

    Without ultrasonic (teammate is wiring HC-SR04), depth from the laptop is
    the only source. If depth is stale or unavailable, return a "blocked ahead"
    detection so the reflex loop stops the robot. A robot that halts when it
    can't see is safe; one that keeps driving blind is not.

    Once ultrasonic is wired, uncomment the merge logic to use it as the
    primary onboard source.
    """
    # ultra = ultrasonic.read_ultrasonic_detections()  # commented out — teammate wiring HC-SR04
    depth = _get_bridge()._get_depth_if_fresh()

    # if ultrasonic.is_available():
    #     if depth is not None:
    #         return ultra + depth
    #     return ultra
    # elif depth is not None:
    if depth is not None:
        return depth
    else:
        return [Detection(
            label="obstacle",
            bbox=(0.0, 0.0, 0.0, 0.0),
            distance_m=0.0,
            bearing_deg=0.0,
        )]
