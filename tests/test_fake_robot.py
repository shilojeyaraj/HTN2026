"""Unit tests for the fake robot (control/fake_robot.py).

Pure logic, no network. Verifies the simulated physics: forward/backward
movement, turn, obstacle collision, reflex stop, and detection readout.
"""

from control.fake_robot import FakeRobot, Obstacle, RobotConfig


def _make_robot(obstacles=None, start=(0.5, 0.5, 0.0)):
    cfg = RobotConfig(realtime=False)
    return FakeRobot(room=(4.0, 3.0), obstacles=obstacles or [], start=start, config=cfg)


class TestMovement:
    def test_forward_moves_position(self):
        robot = _make_robot(start=(0.5, 0.5, 0.0))
        result = robot.forward(1.0)
        assert result["status"] == "completed"
        assert robot.x > 0.5

    def test_backward_moves_position(self):
        robot = _make_robot(start=(2.0, 0.5, 0.0))
        result = robot.backward(0.5)
        assert result["status"] == "completed"
        assert robot.x < 2.0

    def test_turn_changes_heading(self):
        robot = _make_robot(start=(1.0, 1.0, 0.0))
        result = robot.turn(90.0)
        assert result["status"] == "completed"
        assert abs(result["degrees_turned"] - 90.0) < 1.0

    def test_turn_negative_is_right(self):
        robot = _make_robot(start=(1.0, 1.0, 0.0))
        result = robot.turn(-90.0)
        assert result["status"] == "completed"
        assert result["degrees_turned"] < 0

    def test_stop_halts(self):
        robot = _make_robot()
        result = robot.stop()
        assert result["status"] == "stopped"


class TestObstacleAvoidance:
    def test_forward_stops_at_obstacle(self):
        obstacles = [Obstacle(x=1.5, y=0.5, r=0.25)]
        robot = _make_robot(obstacles=obstacles, start=(0.5, 0.5, 0.0))
        result = robot.forward(3.0)
        assert result["status"] == "stopped_by_obstacle"
        assert robot.x < 1.5

    def test_backward_does_not_trigger_reflex_stop(self):
        obstacles = [Obstacle(x=0.5, y=0.5, r=0.25)]
        robot = _make_robot(obstacles=obstacles, start=(1.5, 0.5, 0.0))
        result = robot.backward(0.5)
        assert result["status"] == "completed"


class TestDetections:
    def test_get_detections_returns_obstacles_in_range(self):
        obstacles = [Obstacle(x=1.0, y=0.5, r=0.25), Obstacle(x=10.0, y=10.0, r=0.25)]
        robot = _make_robot(obstacles=obstacles, start=(0.5, 0.5, 0.0))
        dets = robot.get_detections()
        assert len(dets) == 1
        assert dets[0]["distance"] < 2.5

    def test_get_detections_empty_when_no_obstacles(self):
        robot = _make_robot()
        assert robot.get_detections() == []

    def test_reflex_clearance_open_path(self):
        robot = _make_robot()
        assert robot.reflex_clearance() > 0.3

    def test_reflex_clearance_blocked(self):
        obstacles = [Obstacle(x=1.0, y=0.5, r=0.25)]
        robot = _make_robot(obstacles=obstacles, start=(0.5, 0.5, 0.0))
        assert robot.reflex_clearance() < 0.5


class TestState:
    def test_get_state_returns_pose(self):
        robot = _make_robot(start=(1.5, 2.0, 45.0))
        state = robot.get_state()
        assert state["x"] == 1.5
        assert state["y"] == 2.0
        assert state["heading_deg"] == 45.0
