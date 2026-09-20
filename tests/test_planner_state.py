"""Bounded local context replaces per-step retrieval and indexed documents."""

import asyncio
import time
from unittest.mock import AsyncMock, Mock

from brain import loop
from brain.state import RobotState
from control.robomaster import RoboMasterController, RoboMasterError
from tests.test_multimodal_loop import decision, setup_loop


def test_local_history_is_bounded_and_summaries_are_occasional(monkeypatch):
    monkeypatch.setattr(loop, "STARTUP_SCAN_ENABLED", False)
    state = RobotState(current_goal="Find the red chair.", mission_context=["Ground floor search"])
    controller = Mock(spec=RoboMasterController)
    controller.get_chassis_state.return_value = {"position_m": (1, 2, 0)}
    controller.get_camera_state.side_effect = lambda: {"last_frame_monotonic_s": time.monotonic(), "frame_age_s": 0.01}
    controller.turn.return_value = {"status": "completed"}
    model = AsyncMock(return_value=decision())
    enqueue = Mock()
    monkeypatch.setattr(loop, "get_latest_frame", Mock(return_value=b"jpeg"))
    monkeypatch.setattr(loop, "decide_action", model)
    monkeypatch.setattr(loop.brain, "enqueue_memory", enqueue)
    async def run():
        for _ in range(12):
            await loop.run_episode(state, controller)
    asyncio.run(run())
    assert len(state.recent_observations) == len(state.last_actions) == 8
    assert [c.args[0] for c in enqueue.call_args_list] == ["mission_context", "mission_summary"]
    context = model.call_args.args[1]
    assert context["mission_context"] == ["Ground floor search"]
    assert context["prior_action_result"]["name"] == "turn"
    assert context["robot_pose"] == {"position_m": (1, 2, 0)}


def test_camera_adjustment_context_outlasts_action_history_and_requires_fresh_view(setup_loop):
    controller, _, model, _ = setup_loop
    state = RobotState(current_goal="Pass through the doorway")
    before = "Only nearby floor and the bottom of the doorway are visible."
    model.return_value = decision("move_arm", {"x_mm": 100, "y_mm": 30}, observation=before)

    async def run():
        await loop.run_episode(state, controller)
        controller.move_arm.assert_called_once_with(x_mm=80, y_mm=30)
        assert model.call_args.args[1]["last_camera_adjustment"] is None
        # A subsequent physical action must wait for an image after the arm motion.
        controller.get_camera_state.side_effect = None
        controller.get_camera_state.return_value = {"last_frame_monotonic_s": state.last_frame_at}
        model.return_value = decision("forward", {"distance_m": 0.1},
                                      observation="Forward space and doorway are clear; some floor is visible.")
        await loop.run_episode(state, controller)
        model.assert_awaited_once()
        controller.forward.assert_not_called()
        controller.get_camera_state.side_effect = lambda: {"last_frame_monotonic_s": time.monotonic()}
        state.retry_at = 0
        for _ in range(9):
            await loop.run_episode(state, controller)

    asyncio.run(run())
    metadata = model.call_args.args[1]["last_camera_adjustment"]
    assert metadata["name"] == "move_arm"
    assert metadata["arguments"] == {"x_mm": 80, "y_mm": 30}
    assert metadata["result"]["status"] == "completed" and metadata["observation_before"] == before
    assert all(action["name"] == "forward" for action in state.last_actions)
    assert controller.forward.call_count == 9 and controller.move_arm.call_count == 1
    controller.recenter_arm.assert_not_called()  # No floor-triggered or automatic recentering rule.


def test_manual_and_failed_camera_adjustments_are_reported_without_inventing_pose(setup_loop):
    controller, _, model, _ = setup_loop
    state = RobotState(current_goal="Pass under the table", last_user_command="move arm up 30 mm",
                       scene_description="Old view, before the manual command")

    async def run():
        await loop.run_episode(state, controller)
        model.assert_not_awaited()
        manual = state.last_camera_adjustment
        assert manual["arguments"] == {"x_mm": 0, "y_mm": 30}
        assert manual["result"]["status"] == "completed" and manual["observation_before"] is None

        controller.move_arm.side_effect = RoboMasterError("partial arm movement")
        model.return_value = decision("move_arm", {"x_mm": 0, "y_mm": -20},
                                      observation="The tabletop leaves the frame; clearance is uncertain.")
        await loop.run_episode(state, controller)
        assert model.call_args.args[1]["last_camera_adjustment"] == manual
        failed = state.last_camera_adjustment
        assert failed["result"]["status"] == "error"
        assert "applied_args" not in failed["result"]

        state.retry_at = 0
        model.return_value = decision(None, {}, observation="View remains unclear.")
        await loop.run_episode(state, controller)
        assert model.call_args.args[1]["last_camera_adjustment"] == failed
        # Rejected inputs never reached the arm and must not replace its last attempt.
        rejected = loop._execute_verb("move_arm", {"x_mm": "bad", "y_mm": 30}, state, controller)
        assert rejected["status"] == "rejected" and state.last_camera_adjustment is failed

        state.last_user_command = "recenter arm"
        await loop.run_episode(state, controller)
        assert state.last_camera_adjustment["name"] == "recenter_arm"
        assert state.last_camera_adjustment["arguments"] == {}
        assert state.last_camera_adjustment["result"]["status"] == "completed"
        assert state.last_camera_adjustment["observation_before"] is None

    asyncio.run(run())
