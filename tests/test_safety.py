"""Unit tests for the safety gate (brain/safety.py).

Pure logic, no network. Verifies that forward() is vetoed when an obstacle is
within the clearance cone, and that other verbs pass through unchecked.
"""

from brain.safety import check, MIN_CLEARANCE_M, GATED_VERBS
from brain.state import Detection


def _det(distance_m: float, bearing_deg: float, label: str = "obstacle") -> Detection:
    return Detection(label=label, bbox=(0, 0, 0, 0), distance_m=distance_m, bearing_deg=bearing_deg)


class TestSafetyGate:
    def test_forward_vetoed_when_obstacle_close_and_ahead(self):
        dets = [_det(0.2, 0.0)]
        assert check("forward", {"distance_m": 1.0}, dets) == "VETO"

    def test_forward_ok_when_obstacle_outside_cone(self):
        dets = [_det(0.2, 45.0)]
        assert check("forward", {"distance_m": 1.0}, dets) == "OK"

    def test_forward_ok_when_obstacle_beyond_clearance(self):
        dets = [_det(MIN_CLEARANCE_M + 0.1, 0.0)]
        assert check("forward", {"distance_m": 1.0}, dets) == "OK"

    def test_forward_ok_when_no_detections(self):
        assert check("forward", {"distance_m": 1.0}, []) == "OK"

    def test_forward_vetoed_at_boundary(self):
        dets = [_det(MIN_CLEARANCE_M - 0.01, 29.0)]
        assert check("forward", {"distance_m": 1.0}, dets) == "VETO"

    def test_forward_vetoed_at_bearing_boundary(self):
        dets = [_det(0.2, 29.0)]
        assert check("forward", {"distance_m": 1.0}, dets) == "VETO"

    def test_backward_never_vetoed(self):
        dets = [_det(0.1, 0.0)]
        assert check("backward", {"distance_m": 1.0}, dets) == "OK"

    def test_turn_never_vetoed(self):
        dets = [_det(0.1, 0.0)]
        assert check("turn", {"degrees": 90}, dets) == "OK"

    def test_stop_never_vetoed(self):
        dets = [_det(0.1, 0.0)]
        assert check("stop", {}, dets) == "OK"

    def test_speak_never_vetoed(self):
        dets = [_det(0.1, 0.0)]
        assert check("speak", {"text": "hello"}, dets) == "OK"

    def test_gated_verbs_only_contains_forward(self):
        assert GATED_VERBS == {"forward"}
