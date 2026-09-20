"""Integration test for the full brain loop with a fake RoboMaster controller."""

from unittest.mock import patch

import pytest

from tests.conftest import has_real_key

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not has_real_key("BACKBOARD_API_KEY"), reason="BACKBOARD_API_KEY not set in .env"),
]


class FakeRoboMasterController:
    def get_tof_distances(self):
        return {"tof_mm": (500, 0, 0, 0)}

    def get_chassis_state(self):
        return {"position_m": (0.0, 0.0, 0.0)}

    def forward(self, _meters):
        return {"status": "completed"}

    backward = strafe_left = strafe_right = forward

    def turn(self, _degrees):
        return {"status": "completed"}

    def stop(self):
        return {"status": "completed"}


def test_run_episode_with_fake_robomaster():
    from brain.loop import run_episode
    from brain.state import RobotState

    state = RobotState(
        current_goal="Explore the room and report hazards.",
        last_user_command="move forward and explore the area",
    )
    with patch("brain.loop.get_latest_frame", return_value=b"jpeg"), \
         patch("brain.loop.describe_scene", return_value="A room with obstacles ahead. Free space on the left."):
        state = run_episode(state, FakeRoboMasterController())

    assert state is not None
    assert state.last_user_command is None
