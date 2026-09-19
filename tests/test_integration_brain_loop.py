"""Integration test for the full brain loop with the fake robot.

Runs the deliberative loop (brain/loop.py) against the fake robot simulator
with real Backboard API calls. Requires BACKBOARD_API_KEY in .env.
Run: pytest -m integration -k brain_loop
"""

import os
import time
from unittest.mock import patch

import pytest

from tests.conftest import has_real_key

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not has_real_key("BACKBOARD_API_KEY"), reason="BACKBOARD_API_KEY not set in .env"),
]


def test_run_episode_with_fake_robot():
    """Run a single deliberative episode with the fake robot and real Backboard brain.

    Patches perception to use the fake robot's detections/frame instead of the
    OAK-D camera, and patches the arbiter to use a no-op publish.
    """
    from brain.loop import run_episode
    from brain.state import RobotState
    from control.arbiter import Arbiter
    from control.fake_robot import FakeRobot, Obstacle, RobotConfig

    robot = FakeRobot(
        room=(4.0, 3.0),
        obstacles=[Obstacle(1.6, 1.1, 0.28), Obstacle(2.6, 2.1, 0.30)],
        start=(0.4, 0.4, 30.0),
        config=RobotConfig(realtime=False),
    )

    state = RobotState(
        current_goal=(3.5, 2.5),
        last_user_command="move forward and explore the area",
    )

    arbiter = Arbiter(publish_cmd_vel=lambda l, a: None)

    # Patch perception at the import site (brain.loop imported the names directly)
    fake_detections = [
        {"label": "obstacle", "bbox": (0, 0, 0, 0), "distance_m": 1.0, "bearing_deg": 0.0}
    ]
    with patch("brain.loop.get_latest_frame", return_value=(b"", fake_detections)), \
         patch("brain.loop.get_latest_detections", return_value=fake_detections), \
         patch("brain.loop.describe_scene", return_value="A room with obstacles ahead. Free space on the left."):
        state = run_episode(state, arbiter)

    assert state is not None
    print(f"\n  Episode completed. Safety status: {state.safety_status}")
    print(f"  User command consumed: {state.last_user_command is None}")
