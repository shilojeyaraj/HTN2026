"""Verb -> Twist -> arbiter, blocking until the verb self-completes (CLAUDE.md section 6).
Bounded, self-completing verbs are what let Inner Monologue work: each call returns a real
status (`completed` or `stopped_by_obstacle`) for the brain to react to."""

import math
import time

FORWARD_SPEED_MPS = 0.3
TURN_RATE_DPS = 60.0
STOP_DISTANCE_M = 0.3
POLL_HZ = 20


def _drive(arbiter, get_detections, linear: float, angular: float, duration_s: float) -> dict:
    start = time.monotonic()
    while time.monotonic() - start < duration_s:
        if linear > 0:
            blocking = next(
                (d for d in get_detections() if abs(d["bearing_deg"]) < 30 and d["distance_m"] < STOP_DISTANCE_M),
                None,
            )
            if blocking:
                arbiter.set_brain_cmd(0.0, 0.0)
                return {"status": "stopped_by_obstacle", "distance_m": blocking["distance_m"]}
        arbiter.set_brain_cmd(linear, angular)
        time.sleep(1.0 / POLL_HZ)
    arbiter.set_brain_cmd(0.0, 0.0)
    return {"status": "completed"}


def execute_verb(name: str, args: dict, arbiter, get_detections) -> dict:
    if name == "forward":
        return _drive(arbiter, get_detections, FORWARD_SPEED_MPS, 0.0, args["distance_m"] / FORWARD_SPEED_MPS)
    if name == "backward":
        return _drive(arbiter, get_detections, -FORWARD_SPEED_MPS, 0.0, args["distance_m"] / FORWARD_SPEED_MPS)
    if name == "turn":
        angular = math.copysign(1.0, args["degrees"])
        return _drive(arbiter, get_detections, 0.0, angular, abs(args["degrees"]) / TURN_RATE_DPS)
    if name == "stop":
        arbiter.set_brain_cmd(0.0, 0.0)
        return {"status": "completed"}
    return {"status": "error", "detail": f"unknown verb {name}"}
