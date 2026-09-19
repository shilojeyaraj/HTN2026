"""Thread-safe shared buffer bridging the Pi capture pipeline to the robot's
perception and safety loops.

pi/client.py pushes JPEG frames and depth results here as they stream to/from
the laptop. perception/camera.py reads from here for get_latest_frame() and
get_latest_detections(). This replaces the old CSI CameraBridge that ran its
own rpicam-vid capture — the USB webcam pipeline in pi/client.py is now the
single capture path.

Staleness: depth results older than MAX_DEPTH_AGE_S are treated as stale.
The reflex loop fails closed (returns a "blocked ahead" detection) when depth
is stale and ultrasonic is unavailable.
"""

import threading
import time

MAX_FRAME_AGE_S = 2.0
MAX_DEPTH_AGE_S = 2.0


class DepthBuffer:
    """Thread-safe store for the latest JPEG frame and depth result."""

    def __init__(self):
        self._lock = threading.Lock()
        self._latest_jpeg: bytes = b""
        self._latest_depth: dict | None = None
        self._depth_time: float = 0.0
        self._frame_time: float = 0.0

    def push_frame(self, jpeg: bytes) -> None:
        with self._lock:
            self._latest_jpeg = jpeg
            self._frame_time = time.monotonic()

    def push_depth(self, result: dict) -> None:
        with self._lock:
            self._latest_depth = result
            self._depth_time = time.monotonic()

    def get_frame(self) -> bytes:
        with self._lock:
            return self._latest_jpeg

    def get_depth(self) -> tuple[dict | None, float]:
        """Returns (depth_result, age_seconds). None if no result yet."""
        with self._lock:
            if self._latest_depth is None:
                return None, float("inf")
            return self._latest_depth, time.monotonic() - self._depth_time

    def get_depth_if_fresh(self, max_age_s: float = MAX_DEPTH_AGE_S) -> dict | None:
        """Returns the depth result if it exists and is younger than max_age_s."""
        with self._lock:
            if self._latest_depth is None:
                return None
            if time.monotonic() - self._depth_time > max_age_s:
                return None
            return self._latest_depth


_buffer: DepthBuffer | None = None


def get_buffer() -> DepthBuffer:
    """Singleton accessor — same buffer across all modules."""
    global _buffer
    if _buffer is None:
        _buffer = DepthBuffer()
    return _buffer
