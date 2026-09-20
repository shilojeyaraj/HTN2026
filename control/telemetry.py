"""Telemetry: brain activity events, sensor state, and pattern insights.

Shared buffers that the brain loop writes to and the map server reads from,
so the frontend can display what the brain is doing in real-time.
"""

import threading
import time
from copy import deepcopy
from collections import deque


def rover_snapshot(controller, state):
    mission = state.telemetry.snapshot()
    mission["retry_in_s"] = max(0.0, state.retry_at - time.monotonic())
    return {"schema": "rover.v1", "timestamp": time.time(),
            "rover": controller.get_telemetry(), "mission": mission}


class MissionTelemetry:
    """Small, thread-safe mission snapshot shared with the dashboard publisher."""

    def __init__(self):
        self._lock = threading.Lock()
        self._state = {"phase": "idle", "reason": None, "mode": None, "goal": None,
                       "model": None, "scene": None, "scene_at": None, "findings": [],
                       "search_active": False, "search_rotation_deg": 0.0,
                       "retry_in_s": 0.0, "failures": 0, "cycles": 0,
                       "inference_ms": None, "last_command": None}
        # ponytail: recent history is in memory; persist events if cross-run history is needed.
        self._actions = deque(maxlen=40)
        self._sequence = 0

    def update(self, **fields):
        with self._lock:
            self._state.update(fields)

    def start_action(self, name, args, direct):
        with self._lock:
            self._sequence += 1
            event = {"id": self._sequence, "name": str(name), "requested_args": repr(args),
                     "applied_args": None, "mode": "DIRECT" if direct else "CLOSED_LOOP",
                     "status": "executing", "started_at": time.time(), "finished_at": None,
                     "duration_ms": None, "result": None}
            self._actions.append(event)
            self._state.update(phase="executing", reason=str(name))
            return event["id"]

    def finish_action(self, action_id, result, elapsed_ms):
        with self._lock:
            event = next(e for e in self._actions if e["id"] == action_id)
            status = result.get("status", "read")
            if event["name"] == "speak" and status == "completed":
                status = "queued"  # Playback runs separately; completion is not observed here.
            event.update(result=result, status=status,
                         finished_at=time.time(), duration_ms=elapsed_ms)

    def apply_action(self, action_id, args):
        with self._lock:
            event = next(e for e in self._actions if e["id"] == action_id)
            event["applied_args"] = dict(args)

    def snapshot(self):
        with self._lock:
            return {**deepcopy(self._state), "actions": deepcopy(list(self._actions))}


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
