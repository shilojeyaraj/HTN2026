"""Search history informs the planner without overriding its bounded actions."""

import asyncio

import pytest

from brain import loop
from brain.state import RobotState
from control.robomaster import RoboMasterError
from tests.test_multimodal_loop import decision, setup_loop


def test_viewpoint_recovery_direction_changes_and_target_tracking(setup_loop):
    controller, _, model, _ = setup_loop
    state = RobotState(current_goal="Where is the red chair?")

    async def run():
        model.return_value = decision("move_arm", {"x_mm": 0, "y_mm": 30},
                                      observation="Floor fills the view.", target_visible=False, search_active=True)
        await loop.run_episode(state, controller)
        controller.move_arm.assert_called_once_with(x_mm=0, y_mm=30)
        controller.turn.assert_not_called()
        assert state.search_active and state.search_direction == state.search_rotation_deg == 0

        model.return_value = decision(args={"degrees": -200}, target_visible=False, search_active=True)
        await loop.run_episode(state, controller)
        controller.turn.assert_called_with(degrees=-90)
        assert state.search_direction == -1 and state.search_rotation_deg == 90
        assert state.relative_heading_deg == 270
        assert state.inspected_viewpoints[-1]["relative_heading_deg"] == 0  # Pre-turn image.

        # A legacy response without the optional search flag preserves the active scan.
        model.return_value = decision(args={"degrees": -30}, target_visible=False)
        await loop.run_episode(state, controller)
        context = model.call_args.args[1]
        assert context["search_direction"] == -1 and context["search_rotation_deg"] == 90
        assert context["relative_heading_deg"] == 270
        assert context["inspected_viewpoints"][0]["observation"] == "Floor fills the view."
        assert len(context["inspected_viewpoints"]) == 2  # Snapshot, not a live list.

        model.return_value = decision(args={"degrees": 15}, target_visible=False,
                                      observation="Obstacle to the right; inspect the left opening.", search_active=True)
        await loop.run_episode(state, controller)
        controller.turn.assert_called_with(degrees=15)  # Direction is a preference, not a lock.
        assert state.search_direction == 1 and state.search_rotation_deg == 135
        assert state.relative_heading_deg == 255

        model.return_value = decision("forward", {"distance_m": 0.7}, target_visible=True, search_active=True)
        await loop.run_episode(state, controller)
        controller.forward.assert_called_once_with(0.7)
        assert not state.search_active and state.search_rotation_deg == 135
        assert len(state.inspected_viewpoints) == 5  # Acquiring a target preserves search history.
        controller.recenter_arm.assert_not_called()

        model.return_value = decision(None, {}, target_visible=True, goal_complete=True)
        await loop.run_episode(state, controller)
        await loop.run_episode(state, controller)
        assert state.finished_goal == state.current_goal and not state.search_active
        assert model.await_count == 6

    asyncio.run(run())


def test_full_rotation_is_context_not_automatic_completion_and_history_outlasts_recent_actions(setup_loop):
    controller, _, model, _ = setup_loop
    state = RobotState(current_goal="Search for the chair")

    async def run():
        for step in range(12):
            model.return_value = decision(args={"degrees": 30}, observation=f"View {step}",
                                          target_visible=False, search_active=True)
            await loop.run_episode(state, controller)
        assert state.search_rotation_deg == 360 and state.relative_heading_deg == 0
        assert state.finished_goal is None and len(state.last_actions) == 8
        model.return_value = decision("move_arm", {"x_mm": 0, "y_mm": 20},
                                      target_visible=False, search_active=True)
        await loop.run_episode(state, controller)
        context = model.call_args.args[1]
        assert context["inspected_viewpoints"][0]["observation"] == "View 0"
        assert [v["relative_heading_deg"] for v in context["inspected_viewpoints"]] == list(range(0, 360, 30))
        assert context["inspected_viewpoints"][0]["robot_pose"] == {"position_m": (1, 2, 0)}
        controller.move_arm.assert_called_once_with(x_mm=0, y_mm=20)
        assert state.finished_goal is None and state.search_active

        state.current_goal = "Inspect the doorway"
        model.return_value = decision(None, {}, target_visible=False, search_active=False)
        await loop.run_episode(state, controller)
        context = model.call_args.args[1]
        assert not context["search_active"] and context["inspected_viewpoints"] == []
        assert context["search_direction"] == context["search_rotation_deg"] == context["relative_heading_deg"] == 0
        assert state.search_goal == state.current_goal

    asyncio.run(run())


@pytest.mark.parametrize("failure", ["model", "malformed", "hardware", "stale_frame"])
def test_search_failures_do_not_invent_completed_turns_or_viewpoints(failure, setup_loop):
    controller, _, model, _ = setup_loop
    model.return_value = decision(args={"degrees": -45}, target_visible=False, search_active=True)
    state = RobotState(current_goal="Look for the chair")

    async def run():
        await loop.run_episode(state, controller)
        if failure == "model":
            model.side_effect = RuntimeError("temporarily unavailable")
        elif failure == "malformed":
            model.return_value = decision(target_visible=False, search_active="true")
        elif failure == "hardware":
            controller.turn.side_effect = RoboMasterError("partial turn, link lost")
        else:
            controller.get_camera_state.side_effect = None
            controller.get_camera_state.return_value = {"last_frame_monotonic_s": state.last_frame_at}
        await loop.run_episode(state, controller)

    asyncio.run(run())
    assert state.search_active and state.search_direction == -1 and state.search_rotation_deg == 45
    assert state.relative_heading_deg == (None if failure == "hardware" else 315)
    assert len(state.inspected_viewpoints) == (2 if failure == "hardware" else 1)
    assert state.finished_goal is None and not state.scene_fresh


def test_direct_override_updates_heading_without_claiming_a_searched_view(setup_loop):
    controller, _, model, _ = setup_loop
    model.return_value = decision(args={"degrees": 45}, target_visible=False, search_active=True)
    state = RobotState(current_goal="Find chair")

    async def run():
        await loop.run_episode(state, controller)
        state.last_user_command = "turn right 90"
        await loop.run_episode(state, controller)
        assert state.relative_heading_deg == 315
        assert state.search_rotation_deg == 45 and state.search_direction == 1
        assert len(state.inspected_viewpoints) == 1 and model.await_count == 1
        state.last_user_command = "stop"
        await loop.run_episode(state, controller)
        assert state.finished_goal == state.current_goal and not state.search_active

    asyncio.run(run())


def test_view_history_is_bounded_independently_of_action_history(setup_loop):
    controller, _, model, _ = setup_loop
    state = RobotState(current_goal="Search for the chair")
    async def run():
        for step in range(loop.MAX_INSPECTED_VIEWPOINTS + 2):
            model.return_value = decision(None, {}, observation=f"View {step}",
                                          target_visible=False, search_active=True)
            await loop.run_episode(state, controller)
    asyncio.run(run())
    assert len(state.inspected_viewpoints) == loop.MAX_INSPECTED_VIEWPOINTS
    assert state.inspected_viewpoints[0]["observation"] == "View 2"
    assert not state.last_actions
    controller.turn.assert_not_called()


def test_success_after_partial_turn_failure_keeps_heading_unknown(setup_loop):
    controller, _, model, _ = setup_loop
    model.return_value = decision(args={"degrees": 30}, target_visible=False, search_active=True)
    state = RobotState(current_goal="Find chair")
    async def run():
        controller.turn.side_effect = RoboMasterError("partial turn")
        await loop.run_episode(state, controller)
        state.retry_at = 0
        controller.turn.side_effect = None
        await loop.run_episode(state, controller)
    asyncio.run(run())
    assert state.relative_heading_deg is None
    assert model.call_args.args[1]["relative_heading_deg"] is None
    assert state.search_rotation_deg == 30
