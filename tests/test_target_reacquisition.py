"""Approach loss reuses the scan and same-frame handoff, with mocked hardware."""

import asyncio
import logging
import time
from unittest.mock import call

import pytest

from brain import loop
from brain.state import RobotState
from control.robomaster import RoboMasterError
from shared.inference import InferenceUnavailable
from tests.test_multimodal_loop import decision, setup_loop
from tests.test_startup_scan import detection, semantic
from tests.test_target_alignment import target


@pytest.mark.parametrize("lost_decision", [
    decision("forward", {"distance_m": 0.5}, target_visible=False, search_active=False),
    decision(None, {}, target_visible=False, goal_complete=True),
])
def test_loss_stops_scan_reacquires_and_can_interrupt_again(lost_decision, setup_loop, caplog):
    controller, _, model, memory = setup_loop
    state = RobotState(current_goal="Approach red chair", startup_scan_status="target_found")
    state.world_state.robot["heading_deg"] = 120

    async def run():
        model.return_value = decision("forward", {"distance_m": 0.3}, target_alignment=target(0.5, False),
                                      world_observation=semantic([detection()]))
        await loop.run_episode(state, controller)
        assert state.target_tracking == "approaching" and state.target_aligned
        world = state.world_state
        entity = dict(world.entities[0])
        state.relative_heading_deg = 30

        model.return_value = lost_decision
        await loop.run_episode(state, controller)
        assert controller.method_calls[-3:] == [call.stop(), call.recenter_arm(), call.move_arm(x_mm=40, y_mm=30)]
        controller.forward.assert_called_once_with(0.3)
        assert state.finished_goal is None and state.search_active
        assert state.target_tracking == "reacquiring" and state.startup_scan_status == "scanning"
        assert not state.target_aligned and state.active_target is None
        assert state.relative_heading_deg == 30 and world.robot["heading_deg"] == 120
        assert state.world_state is world and world.entities[0] == entity and world.bearings_stale
        assert model.await_count == 2
        assert model.call_args.args[1]["target_tracking"] == "approaching"

        # A buffered pre-camera-motion image cannot advance the scan or reacquire.
        controller.get_camera_state.side_effect = None
        controller.get_camera_state.return_value = {"last_frame_monotonic_s": state.last_frame_at}
        await loop.run_episode(state, controller)
        assert model.await_count == 2 and state.startup_scan_rotation_deg == 0
        controller.get_camera_state.side_effect = lambda: {"last_frame_monotonic_s": time.monotonic()}
        state.retry_at = 0
        memory.enqueue_memory.side_effect = AssertionError("scan must use local state")

        model.return_value = decision("forward", {"distance_m": 0.5}, target_visible=False,
                                      world_observation=semantic())
        for height in ("LOW", "HIGH"):
            await loop.run_episode(state, controller)
            context = model.call_args.args[1]
            assert context["target_tracking"] == "reacquiring" and context["startup_scan"]["active"]
            assert context["world_state"]["robot"]["camera_height"] == height
        controller.turn.assert_called_once_with(degrees=60)
        assert state.search_rotation_deg == state.startup_scan_rotation_deg == 60
        assert world.robot["heading_deg"] == 180 and state.relative_heading_deg == 90
        controller.forward.assert_called_once()

        # Reacquisition interrupts immediately with one new inference and one action.
        model.return_value = decision("forward", {"distance_m": 0.2}, target_alignment=target(0.5, False),
                                      world_observation=semantic())
        arm_calls, turns = controller.move_arm.call_count, controller.turn.call_count
        await loop.run_episode(state, controller)
        assert model.await_count == 5 and state.target_tracking == "approaching"
        assert state.startup_scan_status == "target_found" and not state.search_active and state.target_aligned
        assert controller.forward.call_args == call(0.2)
        assert controller.move_arm.call_count == arm_calls and controller.turn.call_count == turns

        memory.enqueue_memory.side_effect = None
        model.return_value = lost_decision
        await loop.run_episode(state, controller)
        assert controller.stop.call_count == 2 and controller.forward.call_count == 2
        assert state.startup_scan_status == "scanning" and state.startup_scan_rotation_deg == 0
        assert state.target_tracking == "reacquiring" and world.robot["heading_deg"] == 180

    with caplog.at_level(logging.INFO):
        asyncio.run(run())
    assert "Target lost during approach" in caplog.text and "Target reacquired" in caplog.text
    memory.run_tools.assert_not_awaited()


def test_full_unsuccessful_scan_cannot_resume_blind_motion_or_complete_goal(setup_loop):
    controller, _, model, _ = setup_loop
    state = RobotState(current_goal="Approach red chair")

    async def run():
        model.return_value = decision("forward", {"distance_m": 0.2})
        await loop.run_episode(state, controller)
        model.return_value = decision(None, {}, target_visible=False, goal_complete=True,
                                      world_observation=semantic())
        await loop.run_episode(state, controller)
        for _ in range(12):
            await loop.run_episode(state, controller)
        assert controller.turn.call_args_list == [call(degrees=60)] * 6
        assert state.startup_scan_status == "completed" and state.target_tracking == "reacquiring"
        assert state.finished_goal is None and state.search_active
        assert state.search_rotation_deg == 360

        # A false completion after the scan also cannot end this mission.
        await loop.run_episode(state, controller)
        assert state.finished_goal is None
        for name in ("forward", "backward", "strafe_left", "strafe_right"):
            model.return_value = decision(name, {"distance_m": 0.5}, target_visible=False, search_active=False)
            await loop.run_episode(state, controller)
            assert state.last_action_result["name"] == "stop" and state.search_active
        controller.forward.assert_called_once_with(0.2)
        controller.backward.assert_not_called()
        controller.strafe_left.assert_not_called()
        controller.strafe_right.assert_not_called()

        model.return_value = decision(args={"degrees": 30}, target_visible=False)
        await loop.run_episode(state, controller)
        controller.turn.assert_called_with(degrees=30)  # Safe visual search remains available.
        model.return_value = decision("forward", {"distance_m": 0.1})
        await loop.run_episode(state, controller)
        assert state.target_tracking == "approaching" and not state.search_active
        assert controller.forward.call_count == 2

    asyncio.run(run())


@pytest.mark.parametrize("change", ["new_goal", "direct_stop"])
def test_new_goal_and_direct_stop_override_approach_tracking(change, setup_loop):
    controller, _, model, _ = setup_loop
    state = RobotState(current_goal="Approach red chair")

    async def run():
        model.return_value = decision("forward", {"distance_m": 0.2})
        await loop.run_episode(state, controller)
        if change == "new_goal":
            state.current_goal = "Explore the room"
            model.return_value = decision("forward", {"distance_m": 0.1}, target_visible=False)
        else:
            state.last_user_command = "stop"
        await loop.run_episode(state, controller)
        controller.recenter_arm.assert_not_called()
        if change == "new_goal":
            assert state.target_tracking == "idle" and controller.forward.call_count == 2
        else:
            controller.stop.assert_called_once()
            assert state.finished_goal == state.current_goal and model.await_count == 1
            assert state.target_tracking == "idle"

    asyncio.run(run())


def test_failed_stop_cannot_start_a_reacquisition_scan(setup_loop):
    controller, _, model, _ = setup_loop
    state = RobotState(current_goal="Approach red chair")

    async def run():
        model.return_value = decision("forward", {"distance_m": 0.2})
        await loop.run_episode(state, controller)
        controller.stop.side_effect = RoboMasterError("link lost")
        model.return_value = decision(None, {}, target_visible=False)
        with pytest.raises(InferenceUnavailable, match="stop failed"):
            await loop.run_episode(state, controller)
        controller.recenter_arm.assert_not_called()
        controller.turn.assert_not_called()
        controller.forward.assert_called_once()

    asyncio.run(run())
