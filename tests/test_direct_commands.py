"""Explicit local maneuvers skip inference without weakening autonomous execution."""

import asyncio
import json
import logging
import math
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock, call

import pytest

from brain import direct_commands, loop
from brain.direct_commands import decompose_direct_command, parse_direct_command
from brain.state import RobotState
from brain.tools import PHYSICAL_ACTIONS, TOOL_PARAMETERS, validate_tool_args
from control.robomaster import RoboMasterController, RoboMasterError


@pytest.mark.parametrize("text,name,args", [
    ("turn 360", "turn", {"degrees": 360}),
    ("turn 45", "turn", {"degrees": 45}),
    ("turn left 45 degrees", "turn", {"degrees": 45}),
    ("turn right 45 degrees", "turn", {"degrees": -45}),
    ("turn 270 clockwise", "turn", {"degrees": -270}),
    ("turn -90", "turn", {"degrees": -90}),
    ("turn a little", "turn", {"degrees": 15}),
    ("turn left slightly", "turn", {"degrees": 15}),
    ("turn left a little", "turn", {"degrees": 15}),
    ("move forward 1.5 m", "forward", {"distance_m": 1.5}),
    ("move forward slightly", "forward", {"distance_m": 0.2}),
    ("move forward a little", "forward", {"distance_m": 0.2}),
    ("move forward a small amount", "forward", {"distance_m": 0.2}),
    ("move backward a little", "backward", {"distance_m": 0.2}),
    ("strafe right 0.2 m", "strafe_right", {"distance_m": 0.2}),
    ("strafe left 1.8 meters", "strafe_left", {"distance_m": 1.8}),
    (" Please STOP! ", "stop", {}),
    ("open gripper", "open_gripper", {}),
    ("close the claw", "close_gripper", {}),
    ("recenter arm", "recenter_arm", {}),
    ("move arm up 30 mm", "move_arm", {"x_mm": 0, "y_mm": 30}),
])
def test_explicit_commands_parse_locally(text, name, args):
    assert parse_direct_command(text) == {"verb": name, "args": args}


@pytest.mark.parametrize("text", [
    "find the red chair", "approach the person", "search the room", "navigate around the obstacle",
    "inspect the doorway", "locate someone who needs help", "follow the person", "avoid the wall",
    "go over there", "turn left", "move forward", "turn until facing the chair",
    "turn 360 and find the chair", "turn 90 if the path is clear", "don't turn 90",
    "stop when you see a person", "turn right -45", "move forward 1.5 feet", "turn left 45 right",
    "find the red chair, then stop", "move forward a little if clear, then stop",
    "turn 90 then move forward 1 m, then stop", "move forward a little, then stop, then stop",
])
def test_ambiguous_compound_conditional_and_perceptual_goals_are_not_direct(text):
    assert parse_direct_command(text) is None


@pytest.fixture
def local_only(monkeypatch):
    controller = MagicMock(spec=RoboMasterController)
    controller.__enter__.return_value = controller
    for name in PHYSICAL_ACTIONS | {"stop"}:
        getattr(controller, name).return_value = {"status": "completed"}
    camera = Mock(side_effect=AssertionError("direct mode must not capture a frame"))
    vision = AsyncMock(side_effect=AssertionError("direct mode must not call multimodal AI"))
    planner = AsyncMock(side_effect=AssertionError("direct mode must not call Backboard"))
    monkeypatch.setattr(loop, "get_latest_frame", camera)
    monkeypatch.setattr(loop, "decide_action", vision)
    monkeypatch.setattr(loop.brain, "run_tools", planner)
    yield controller
    camera.assert_not_called()
    vision.assert_not_awaited()
    planner.assert_not_awaited()


@pytest.mark.parametrize("goal,name,chunks", [
    ("turn 360", "turn", [{"degrees": 90}] * 4),
    ("turn 45", "turn", [{"degrees": 45}]),
    ("turn left 45 degrees", "turn", [{"degrees": 45}]),
    ("turn -270", "turn", [{"degrees": -90}] * 3),
    ("move forward 1.5 m", "forward", [0.75, 0.75]),
    ("move forward slightly", "forward", [0.2]),
    ("move forward a small amount", "forward", [0.2]),
    ("move forward a little", "forward", [0.2]),
    ("turn left a little", "turn", [{"degrees": 15}]),
    ("move backward slightly", "backward", [0.2]),
    ("strafe right 1.8 m", "strafe_right", [0.75, 0.75, 0.3]),
    ("open gripper", "open_gripper", [{}]),
    ("close gripper", "close_gripper", [{}]),
    ("recenter arm", "recenter_arm", [{}]),
    ("stop", "stop", [{}]),
])
def test_direct_goal_runs_bounded_chunks_once_without_perception(goal, name, chunks, local_only, caplog):
    state = RobotState(current_goal=goal)

    async def run_twice():
        await loop.run_episode(state, local_only)
        await loop.run_episode(state, local_only)

    with caplog.at_level(logging.INFO):
        asyncio.run(run_twice())

    expected = [call(**chunk) if isinstance(chunk, dict) else call(chunk) for chunk in chunks]
    assert getattr(local_only, name).call_args_list == expected
    assert state.finished_goal == goal
    assert state.last_action_result["result"]["status"] == "completed"
    assert state.last_action_result["arguments"] == parse_direct_command(goal)["args"]
    assert state.last_action_result["result"]["completed_chunks"] == len(chunks)
    assert not state.scene_fresh  # Open-loop execution never fakes a camera observation.
    assert "execution mode=DIRECT" in caplog.text
    assert "total requested=" in caplog.text and "local chunks=" in caplog.text
    assert "DIRECT execution finished duration_s=" in caplog.text


@pytest.mark.parametrize("goal,expected", [
    ("move forward a small amount, then stop", [call.forward(0.2), call.stop()]),
    ("move forward 1.5 m then stop", [call.forward(0.75), call.forward(0.75), call.stop()]),
    ("turn left a little, then stop", [call.turn(degrees=15), call.stop()]),
    ("turn 360, then stop", [call.turn(degrees=90)] * 4 + [call.stop()]),
    ("open gripper, then stop", [call.open_gripper(), call.stop()]),
    ("turn 0, then stop", [call.stop()]),
])
def test_trailing_stop_executes_locally_after_bounded_maneuver(goal, expected, local_only):
    command = parse_direct_command(goal)
    assert command["then_stop"] is True
    assert decompose_direct_command(command)[-1] == {"verb": "stop", "args": {}}

    state = asyncio.run(loop.run_episode(RobotState(current_goal=goal), local_only))

    assert local_only.mock_calls == expected
    assert state.finished_goal == goal
    assert state.last_action_result["result"]["status"] == "completed"


@pytest.mark.parametrize("total", [0.75, 0.751, 0.76, 1.5, 1.51, 1.8])
def test_translation_chunks_preserve_total_even_with_tiny_remainders(total):
    chunks = decompose_direct_command({"verb": "forward", "args": {"distance_m": total}})
    values = [chunk["args"]["distance_m"] for chunk in chunks]
    assert math.isclose(sum(values), total)
    for chunk in chunks:
        assert 0.05 <= chunk["args"]["distance_m"] <= 0.75
        assert validate_tool_args(chunk["verb"], chunk["args"]) == chunk["args"]


@pytest.mark.parametrize("total", [-1, 0.01, float("inf"), float("nan"), True, "bad", 1e20])
def test_invalid_or_unreasonably_large_totals_are_rejected_before_moving(total):
    with pytest.raises(ValueError):
        decompose_direct_command({"verb": "forward", "args": {"distance_m": total}})


def test_chunking_uses_live_schema_bounds_and_configured_slight_defaults(monkeypatch):
    monkeypatch.setitem(TOOL_PARAMETERS["turn"]["properties"]["degrees"], "maximum", 30)
    chunks = decompose_direct_command(parse_direct_command("turn 90"))
    assert [c["args"]["degrees"] for c in chunks] == [30, 30, 30]
    monkeypatch.setattr(direct_commands, "SLIGHT_TRANSLATION_M", 0.1)
    monkeypatch.setattr(direct_commands, "SLIGHT_TURN_DEG", 10)
    assert parse_direct_command("move forward slightly")["args"] == {"distance_m": 0.1}
    assert parse_direct_command("turn slightly")["args"] == {"degrees": 10}


@pytest.mark.parametrize("goal,status", [("turn 0", "completed"), ("move forward 0 m", "completed"),
                                        ("move forward 0.01 m", "rejected"), ("turn 9001", "rejected")])
def test_zero_or_rejected_direct_goal_never_moves(goal, status, local_only):
    state = asyncio.run(loop.run_episode(RobotState(current_goal=goal), local_only))
    assert local_only.mock_calls == []
    assert state.finished_goal == goal
    assert state.last_action_result["result"]["status"] == status


def test_partial_failure_stops_and_does_not_retry_remaining_chunks(local_only):
    local_only.turn.side_effect = [{"status": "completed"}, RoboMasterError("link lost")]
    state = RobotState(current_goal="turn 360")

    async def run():
        await loop.run_episode(state, local_only)
        await loop.run_episode(state, local_only)

    asyncio.run(run())
    assert local_only.turn.call_count == 2
    local_only.stop.assert_called_once()
    assert state.last_action_result["result"]["status"] == "error"
    assert state.last_action_result["arguments"] == {"degrees": 360}
    assert state.last_action_result["result"]["completed_chunks"] == 1


def test_interrupted_maneuver_requests_stop(local_only):
    local_only.turn.side_effect = KeyboardInterrupt
    with pytest.raises(KeyboardInterrupt):
        asyncio.run(loop.run_episode(RobotState(current_goal="turn 360"), local_only))
    local_only.turn.assert_called_once()
    local_only.stop.assert_called_once()


def test_direct_spoken_override_is_consumed_and_stop_ends_autonomous_goal(local_only):
    state = RobotState(current_goal="find the chair", last_user_command="turn left 45 degrees")
    asyncio.run(loop.run_episode(state, local_only))
    assert state.last_user_command is None and state.finished_goal is None
    state.last_user_command = "stop"
    asyncio.run(loop.run_episode(state, local_only))
    assert state.finished_goal == "find the chair"
    local_only.stop.assert_called_once()


def test_main_exits_after_one_direct_goal_before_vision_cooldown(local_only, monkeypatch):
    import main

    monkeypatch.setattr("sys.argv", ["main.py", "--goal", "turn 360"])
    monkeypatch.setattr(main, "RoboMasterController", lambda: local_only)
    monkeypatch.setattr(main, "MapServer", MagicMock())
    monkeypatch.setattr(main, "brain", SimpleNamespace(aclose=AsyncMock()))
    cooldown = Mock(side_effect=AssertionError("direct goal should already be finished"))
    monkeypatch.setattr(main.asyncio, "sleep", cooldown)
    monkeypatch.setattr(main, "aclose_vision_client", AsyncMock())

    asyncio.run(main.main())

    assert local_only.turn.call_count == 4
    local_only.__exit__.assert_called_once()
    main.brain.aclose.assert_awaited_once()
    cooldown.assert_not_called()
