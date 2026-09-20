"""Target-specific centering uses local state; all hardware and inference are mocked."""

import asyncio
import json
import logging

import pytest

from brain import loop
from brain.state import RobotState
from brain.tools import validate_decision
from tests.test_multimodal_loop import decision, setup_loop


def target(x, correcting=True, target_id="red-chair"):
    return {"target_id": target_id, "center_x": x, "turn_for_alignment": correcting}


def test_alignment_jitter_is_suppressed_then_approach_and_clear_drift_resume(setup_loop, caplog):
    controller, _, model, memory = setup_loop
    state = RobotState(current_goal="Approach the red chair")

    async def run():
        for x in (0.50, 0.39, 0.61, 0.35, 0.65):
            model.return_value = decision(args={"degrees": 30}, target_alignment=target(x))
            await loop.run_episode(state, controller)
            assert state.target_aligned and state.last_alignment_action["correction_deg"] == 0
        controller.turn.assert_not_called()
        assert state.relative_heading_deg == 0

        # The next safe task step comes from this fresh image, not an invented drive.
        model.return_value = decision("forward", {"distance_m": 0.3}, target_alignment=target(0.62, False))
        await loop.run_episode(state, controller)
        controller.forward.assert_called_once_with(0.3)
        context = model.call_args.args[1]["alignment_state"]
        assert context["active_target"] == "red-chair" and context["target_aligned"]
        assert context["last_target_position"] == 0.65 and context["last_alignment_action"]["suppressed"]
        assert state.target_aligned  # Keep the latch during forward approach.

        model.return_value = decision(args={"degrees": -30}, target_alignment=target(0.66))
        await loop.run_episode(state, controller)
        assert controller.turn.call_args.kwargs["degrees"] == pytest.approx(-9.6)
        assert not state.target_aligned
        assert context["target_aligned"]  # Previous planner context is a snapshot.

        model.return_value = decision(args={"degrees": -30}, target_alignment=target(0.62))
        await loop.run_episode(state, controller)
        assert controller.turn.call_args.kwargs["degrees"] == pytest.approx(-7.2)
        assert not state.target_aligned  # Must enter 0.40–0.60 again to latch.

    with caplog.at_level(logging.INFO):
        asyncio.run(run())
    assert model.await_count == 8 and controller.turn.call_count == 2
    memory.run_tools.assert_not_awaited()
    for message in ("position=roughly_centered", "position=left", "position=right",
                    "within_deadband=True", "hysteresis_suppressed=True", "correction_deg="):
        assert message in caplog.text


@pytest.mark.parametrize("x,requested,expected", [
    (0, 90, 30), (0.2, 90, 18), (0.39, 90, 6.6), (0.4, 30, None),
    (0.6, -30, None), (0.61, -90, -6.6), (0.8, -90, -18), (1, -90, -30),
    (0.1, 3, 3), (0.1, -90, 24),  # Preserve a smaller safe request; correct wrong sign.
])
def test_corrections_scale_with_offset_and_center_band_includes_boundaries(x, requested, expected, setup_loop):
    controller, _, model, _ = setup_loop
    model.return_value = decision(args={"degrees": requested}, target_alignment=target(x))
    state = asyncio.run(loop.run_episode(RobotState(current_goal="Approach chair"), controller))
    if expected is None:
        controller.turn.assert_not_called()
        assert state.target_aligned
    else:
        assert controller.turn.call_args.kwargs["degrees"] == pytest.approx(expected)
        assert not state.target_aligned
    controller.forward.assert_not_called()  # A suppressed turn cannot authorize blind motion.


@pytest.mark.parametrize("change", ["goal", "target", "lost", "unknown", "direct", "navigation", "camera"])
def test_alignment_resets_when_prior_view_or_target_no_longer_applies(change, setup_loop):
    controller, _, model, _ = setup_loop
    state = RobotState(current_goal="Approach chair")

    async def run():
        model.return_value = decision(None, {}, target_alignment=target(0.5, False))
        await loop.run_episode(state, controller)
        assert state.target_aligned
        if change == "goal":
            state.current_goal = "Inspect chair"
        elif change in {"lost", "unknown"}:
            model.return_value = decision(None, {}, target_visible=change == "unknown")
            await loop.run_episode(state, controller)
            assert state.active_target is None and not state.target_aligned
        elif change == "direct":
            state.last_user_command = "turn right 60"
            await loop.run_episode(state, controller)
            controller.turn.assert_called_with(degrees=-60)
        elif change == "navigation":
            model.return_value = decision(args={"degrees": 70}, target_alignment=target(0.5, False))
            await loop.run_episode(state, controller)
            controller.turn.assert_called_with(degrees=70)  # Never cap an obstacle/navigation turn.
        elif change == "camera":
            model.return_value = decision("move_arm", {"x_mm": 0, "y_mm": 10}, target_alignment=target(0.5, False))
            await loop.run_episode(state, controller)
        model.return_value = decision(args={"degrees": -30},
                                      target_alignment=target(0.62, target_id="blue-chair" if change == "target" else "red-chair"))
        await loop.run_episode(state, controller)
        assert controller.turn.call_args.kwargs["degrees"] == pytest.approx(-7.2)
        assert not state.target_aligned

    asyncio.run(run())


def test_stale_frame_cannot_update_alignment_or_start_approach(setup_loop):
    controller, _, model, _ = setup_loop
    state = RobotState(current_goal="Approach chair")

    async def run():
        model.return_value = decision(args={"degrees": 30}, target_alignment=target(0.5))
        await loop.run_episode(state, controller)
        controller.get_camera_state.side_effect = None
        controller.get_camera_state.return_value = {"last_frame_monotonic_s": state.last_frame_at}
        model.return_value = decision("forward", {"distance_m": 0.2}, target_alignment=target(0.5, False))
        await loop.run_episode(state, controller)
        model.assert_awaited_once()
        assert state.target_aligned and not state.scene_fresh
        controller.forward.assert_not_called()

    asyncio.run(run())


@pytest.mark.parametrize("metadata", [
    {}, [], target(True), target("0.5"), target(float("nan")), target(float("inf")),
    target(-0.01), target(1.01), target(0.5, "true"), target(0.5, target_id=" "),
    target(0.5, target_id="x" * 121), {**target(0.5), "extra": True},
])
def test_invalid_target_metadata_rejects_entire_decision(metadata, setup_loop):
    controller, _, model, _ = setup_loop
    model.return_value = decision(target_alignment=metadata)
    state = asyncio.run(loop.run_episode(RobotState(current_goal="Approach chair"), controller))
    controller.turn.assert_not_called()
    assert state.consecutive_failures == 1 and not state.target_aligned


def test_target_metadata_requires_visibility_and_a_matching_action():
    for raw in (decision(target_visible=False, target_alignment=target(0.5)),
                decision("forward", {"distance_m": 0.2}, target_alignment=target(0.5)),
                decision(None, {}, goal_complete=True, target_alignment=target(0.5))):
        with pytest.raises(ValueError):
            validate_decision(raw)
    old_response = json.loads(decision())
    del old_response["target_alignment"]
    with pytest.raises(ValueError):
        validate_decision(json.dumps(old_response))
