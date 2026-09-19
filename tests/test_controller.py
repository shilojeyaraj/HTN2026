"""Unit tests for the controller (control/controller.py).

Pure logic, no network. Uses a fake arbiter and fake detections to verify
that verbs produce the right (linear, angular) commands and return correct
status dicts.
"""

import math
from unittest.mock import MagicMock

from control import controller
from control.controller import execute_verb


class FakeArbiter:
    def __init__(self):
        self.commands = []

    def set_brain_cmd(self, linear, angular):
        self.commands.append((linear, angular))


def _no_detections():
    return []


def _blocking_detection(distance_m=0.2, bearing_deg=0.0):
    return [{"label": "wall", "bbox": (0, 0, 0, 0), "distance_m": distance_m, "bearing_deg": bearing_deg}]


class TestForward:
    def test_completes_short_distance(self):
        arb = FakeArbiter()
        # Patch the poll sleep so the test runs fast
        original_sleep = controller.time.sleep
        controller.time.sleep = lambda _: None
        try:
            result = execute_verb("forward", {"distance_m": 0.05}, arb, _no_detections)
        finally:
            controller.time.sleep = original_sleep
        assert result["status"] == "completed"
        assert arb.commands[-1] == (0.0, 0.0)

    def test_stops_by_obstacle(self):
        arb = FakeArbiter()
        original_sleep = controller.time.sleep
        controller.time.sleep = lambda _: None
        try:
            result = execute_verb("forward", {"distance_m": 5.0}, arb, lambda: _blocking_detection())
        finally:
            controller.time.sleep = original_sleep
        assert result["status"] == "stopped_by_obstacle"
        assert "distance_m" in result
        assert arb.commands[-1] == (0.0, 0.0)


class TestBackward:
    def test_completes_short_distance(self):
        arb = FakeArbiter()
        original_sleep = controller.time.sleep
        controller.time.sleep = lambda _: None
        try:
            result = execute_verb("backward", {"distance_m": 0.05}, arb, _no_detections)
        finally:
            controller.time.sleep = original_sleep
        assert result["status"] == "completed"
        assert arb.commands[-1] == (0.0, 0.0)


class TestTurn:
    def test_completes_small_turn(self):
        arb = FakeArbiter()
        original_sleep = controller.time.sleep
        controller.time.sleep = lambda _: None
        try:
            result = execute_verb("turn", {"degrees": 5.0}, arb, _no_detections)
        finally:
            controller.time.sleep = original_sleep
        assert result["status"] == "completed"
        assert arb.commands[-1] == (0.0, 0.0)


class TestStop:
    def test_stops_immediately(self):
        arb = FakeArbiter()
        result = execute_verb("stop", {}, arb, _no_detections)
        assert result["status"] == "completed"
        assert arb.commands == [(0.0, 0.0)]


class TestUnknownVerb:
    def test_returns_error(self):
        arb = FakeArbiter()
        result = execute_verb("fly", {}, arb, _no_detections)
        assert result["status"] == "error"
