"""Telemetry: brain activity events, sensor state, and pattern insights.

Shared buffers that the brain loop writes to and the map server reads from,
so the frontend can display what the brain is doing in real-time.
"""

import threading
import time
from collections import deque


class BrainActivity:
    """Ring buffer of recent brain tool calls, thread-safe."""

    def __init__(self, maxlen: int = 20):
        self._events: deque[dict] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def log_call(self, tool: str, args: dict, result: dict) -> None:
        with self._lock:
            self._events.append({
                "tool": tool,
                "args": args,
                "result": result,
                "timestamp": time.time(),
            })

    def recent(self, n: int = 10) -> list[dict]:
        with self._lock:
            return list(self._events)[-n:]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


class SensorState:
    """Latest sensor readings, thread-safe."""

    def __init__(self):
        self._lock = threading.Lock()
        self._temperature = {"celsius": 22.0, "status": "ok"}
        self._audio = {"db": 35.0, "event": None}
        self._gyro = {"pitch_deg": 0.0, "roll_deg": 0.0, "tipped": False, "bump": False}

    def update_temperature(self, celsius: float, status: str) -> None:
        with self._lock:
            self._temperature = {"celsius": celsius, "status": status}

    def update_audio(self, db: float, event: dict | None = None) -> None:
        with self._lock:
            self._audio = {"db": db, "event": event}

    def update_gyro(self, pitch: float, roll: float, tipped: bool, bump: bool) -> None:
        with self._lock:
            self._gyro = {"pitch_deg": pitch, "roll_deg": roll, "tipped": tipped, "bump": bump}

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "temperature": self._temperature,
                "audio": self._audio,
                "gyro": self._gyro,
            }


class MissionInsights:
    """Latest pattern analysis result, thread-safe."""

    def __init__(self):
        self._lock = threading.Lock()
        self._insights: dict | None = None

    def update(self, insights: dict) -> None:
        with self._lock:
            self._insights = insights

    def get(self) -> dict | None:
        with self._lock:
            return self._insights
