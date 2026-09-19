"""Unit tests for the reflex loop (control/reflex.py).

Pure logic, no network. Verifies that the reflex loop publishes a stop
override when an obstacle is close and ahead, and clears the override
when the path is clear.
"""

from unittest.mock import MagicMock

from control.reflex import ReflexLoop, STOP_DISTANCE_M


def _det(distance_m, bearing_deg=0.0):
    return {"label": "obstacle", "bbox": (0, 0, 0, 0), "distance_m": distance_m, "bearing_deg": bearing_deg}


class TestReflexTick:
    def test_sets_stop_override_when_obstacle_close_ahead(self):
        arb = MagicMock()
        reflex = ReflexLoop(get_detections=lambda: [_det(0.1, 0.0)], arbiter=arb)
        reflex.tick()
        arb.set_reflex_cmd.assert_called_once_with((0.0, 0.0))

    def test_clears_override_when_path_clear(self):
        arb = MagicMock()
        reflex = ReflexLoop(get_detections=lambda: [], arbiter=arb)
        reflex.tick()
        arb.set_reflex_cmd.assert_called_once_with(None)

    def test_clears_override_when_obstacle_outside_cone(self):
        arb = MagicMock()
        reflex = ReflexLoop(get_detections=lambda: [_det(0.1, 45.0)], arbiter=arb)
        reflex.tick()
        arb.set_reflex_cmd.assert_called_once_with(None)

    def test_clears_override_when_obstacle_far(self):
        arb = MagicMock()
        reflex = ReflexLoop(get_detections=lambda: [_det(STOP_DISTANCE_M + 0.5, 0.0)], arbiter=arb)
        reflex.tick()
        arb.set_reflex_cmd.assert_called_once_with(None)

    def test_stop_just_inside_boundary_distance(self):
        arb = MagicMock()
        reflex = ReflexLoop(get_detections=lambda: [_det(STOP_DISTANCE_M - 0.01, 0.0)], arbiter=arb)
        reflex.tick()
        arb.set_reflex_cmd.assert_called_once_with((0.0, 0.0))

    def test_clears_just_outside_boundary_distance(self):
        arb = MagicMock()
        reflex = ReflexLoop(get_detections=lambda: [_det(STOP_DISTANCE_M + 0.01, 0.0)], arbiter=arb)
        reflex.tick()
        arb.set_reflex_cmd.assert_called_once_with(None)
