"""Untrusted planner calls cannot crash execution or chain motion on stale vision."""

import asyncio
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from backboard.models import ChatMessagesResponse

from brain import loop
from brain.backboard_client import BackboardBrain
from brain.state import RobotState
from brain.tools import PHYSICAL_ACTIONS, TOOL_PARAMETERS, validate_tool_args
from control.robomaster import RoboMasterController, RoboMasterError


@pytest.mark.parametrize("name,args", [
    ("turn", {}), ("turn", {"angle": 30}), ("turn", '{"degrees":'),
    ("turn", "[]"), ("turn", "null"), ("turn", []), ("turn", None),
    ("turn", {"degrees": True}), ("turn", {"degrees": None}),
    ("turn", {"degrees": float("nan")}), ("turn", {"degrees": "Infinity"}),
    ("turn", {"degrees": "abc"}), ("turn", {"degrees": 10 ** 400}),
    ("turn", {"degrees": 5, "speed": 540}),
    ("forward", {}), ("backward", {"distance_m": {}}),
    ("strafe_left", {"distance_m": False}), ("strafe_right", {"distance_m": [1]}),
    ("move_arm", {"x_mm": 10}), ("move_arm", {"y_mm": 10}),
    ("move_arm", {"x_mm": "NaN", "y_mm": 5}),
    ("speak", {}), ("speak", {"text": "   "}), ("speak", {"text": 123}),
    ("stop", {"degrees": 5}), ("drive_speed", {}), (None, {}), ([], {}),
])
def test_malformed_args_are_rejected_without_hardware_or_speech(name, args, monkeypatch):
    controller = Mock(spec=RoboMasterController)
    speech = Mock()
    monkeypatch.setattr(loop, "speak", speech)
    state = RobotState(scene_fresh=True)

    result = loop._execute_verb(name, args, state, controller)

    assert result["status"] == "rejected"
    assert controller.mock_calls == []
    speech.assert_not_called()
    assert state.scene_fresh  # Rejection does not consume a valid view.


def test_missing_degrees_is_logged_with_received_args(caplog):
    with caplog.at_level(logging.INFO):
        result = loop._execute_verb("turn", {"angle": 30}, RobotState(scene_fresh=True), Mock())
    assert "Executing tool=turn args={'angle': 30}" in caplog.text
    assert "Rejected tool=turn args={'angle': 30}: missing required argument(s): degrees" in caplog.text
    assert result["status"] == "rejected"


@pytest.mark.parametrize("name", ["forward", "backward", "strafe_left", "strafe_right"])
@pytest.mark.parametrize("value,expected", [("2.5", 0.5), (0.01, 0.05), ("0.2", 0.2)])
def test_distances_are_coerced_and_clamped_before_hardware(name, value, expected):
    controller = Mock(spec=RoboMasterController)
    getattr(controller, name).return_value = {"status": "completed"}
    result = loop._execute_verb(name, {"distance_m": value}, RobotState(scene_fresh=True), controller)
    getattr(controller, name).assert_called_once_with(expected)
    assert result["applied_args"] == {"distance_m": expected}


def test_turn_arm_and_speech_limits_reach_the_executor(monkeypatch):
    controller = Mock(spec=RoboMasterController)
    controller.turn.return_value = controller.move_arm.return_value = {"status": "completed"}
    speech = Mock()
    monkeypatch.setattr(loop, "speak", speech)

    loop._execute_verb("turn", '{"degrees": "-200"}', RobotState(scene_fresh=True), controller)
    controller.turn.assert_called_once_with(degrees=-45)
    loop._execute_verb("move_arm", {"x_mm": "100", "y_mm": -200}, RobotState(scene_fresh=True), controller)
    controller.move_arm.assert_called_once_with(x_mm=80, y_mm=-80)
    loop._execute_verb("speak", {"text": "x" * 300}, RobotState(), controller)
    speech.assert_called_once_with("x" * 240)
    assert validate_tool_args("turn", {"degrees": 200}) == {"degrees": 45}


def test_schema_bounds_match_execution_limits():
    for name, schema in TOOL_PARAMETERS.items():
        assert schema["additionalProperties"] is False
        for key, bounds in {"distance_m": (0.05, 0.5), "degrees": (-45, 45), "x_mm": (-80, 80), "y_mm": (-80, 80)}.items():
            if key in schema["properties"]:
                rule = schema["properties"][key]
                assert (rule["minimum"], rule["maximum"]) == bounds
                assert key in schema["required"]
    assert TOOL_PARAMETERS["speak"]["properties"]["text"]["maxLength"] == 240


def tool_call(name, args, call_id):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": args}}


def response(*calls):
    return ChatMessagesResponse(messages=[{
        "status": "REQUIRES_ACTION" if calls else "COMPLETED", "content": "",
        "thread_id": "thread", "assistant_id": "assistant", "tool_calls": list(calls),
    }])


def mock_brain(monkeypatch, first_response, *followups):
    planner = BackboardBrain("google", "test-model")
    planner.assistant_id = "assistant"
    planner.client = SimpleNamespace(
        send_message=AsyncMock(return_value=first_response),
        submit_tool_outputs_simple=AsyncMock(side_effect=followups),
    )
    monkeypatch.setattr(loop, "brain", planner)
    monkeypatch.setattr(loop, "get_latest_frame", Mock(return_value=b"jpeg"))
    monkeypatch.setattr(loop, "describe_scene", Mock(return_value="Fresh scene"))
    return planner


def test_physical_action_returns_to_perception_before_followup_planning(monkeypatch):
    planner = mock_brain(monkeypatch, response(
        tool_call("turn", '{"angle": 30}', "bad"),
        tool_call("turn", '{"degrees": 90}', "first"),
        tool_call("forward", '{"distance_m": 0.4}', "skipped"),
    ), response(tool_call("forward", '{"distance_m": 0.2}', "new-plan")))
    controller = Mock(spec=RoboMasterController)
    controller.get_chassis_state.return_value = {}
    controller.turn.return_value = controller.forward.return_value = {"status": "completed"}
    monkeypatch.setattr(loop, "describe_scene", Mock(side_effect=["Before turn", "After turn"]))
    state = RobotState(current_goal="Explore")

    async def two_cycles():
        await loop.run_episode(state, controller)
        controller.turn.assert_called_once_with(degrees=45)
        controller.forward.assert_not_called()
        planner.client.submit_tool_outputs_simple.assert_not_awaited()
        assert state.last_action_result["name"] == "turn"
        assert not state.scene_fresh

        async def resume(**kwargs):
            assert loop.describe_scene.call_count == 2
            assert state.scene_description == "After turn"
            outputs = kwargs["tool_outputs"]
            assert [json.loads(out["output"])["status"] for out in outputs] == ["rejected", "completed", "skipped"]
            fresh_state = json.loads(json.loads(outputs[-1]["output"])["current_scene_and_state"])
            assert fresh_state["scene_description"] == "After turn"
            assert fresh_state["scene_fresh"]
            return response(tool_call("forward", '{"distance_m": 0.2}', "new-plan"))

        planner.client.submit_tool_outputs_simple.side_effect = resume
        await loop.run_episode(state, controller)
        controller.forward.assert_called_once_with(0.2)
        assert state.last_action_result["name"] == "forward"
        planner.client.send_message.assert_awaited_once()
        planner.client.submit_tool_outputs_simple.assert_awaited_once()

    asyncio.run(two_cycles())


@pytest.mark.parametrize("name,args", [
    ("forward", {"distance_m": 0.2}), ("backward", {"distance_m": 0.2}),
    ("strafe_left", {"distance_m": 0.2}), ("strafe_right", {"distance_m": 0.2}),
    ("turn", {"degrees": 30}), ("move_arm", {"x_mm": 10, "y_mm": 0}),
    ("recenter_arm", {}), ("open_gripper", {}), ("close_gripper", {}),
])
def test_every_physical_action_ends_the_cycle(name, args, monkeypatch):
    planner = mock_brain(monkeypatch, response(tool_call("get_state", "{}", "read")), response(
        tool_call(name, json.dumps(args), "physical"),
        tool_call("turn", '{"degrees": -30}', "stale-turn"),
    ))
    controller = Mock(spec=RoboMasterController)
    controller.get_chassis_state.return_value = {}
    getattr(controller, name).return_value = {"status": "completed"}

    asyncio.run(loop.run_episode(RobotState(), controller))

    physical_calls = [call for call in controller.mock_calls if call[0] in PHYSICAL_ACTIONS]
    assert len(physical_calls) == 1
    assert physical_calls[0][0] == name
    planner.client.submit_tool_outputs_simple.assert_awaited_once()  # read-only follow-up only


def test_hardware_failure_still_consumes_the_view(monkeypatch):
    planner = mock_brain(monkeypatch, response(
        tool_call("turn", '{"degrees": 30}', "failed-turn"),
        tool_call("forward", '{"distance_m": 0.2}', "stale-move"),
    ))
    controller = Mock(spec=RoboMasterController)
    controller.get_chassis_state.return_value = {}
    controller.turn.side_effect = RoboMasterError("link lost after partial motion")
    state = RobotState()

    asyncio.run(loop.run_episode(state, controller))

    assert state.last_action_result["result"]["status"] == "error"
    controller.forward.assert_not_called()
    planner.client.submit_tool_outputs_simple.assert_not_awaited()


def test_failed_perception_cannot_authorize_a_second_movement(monkeypatch):
    planner = mock_brain(monkeypatch, response(tool_call("turn", '{"degrees": 20}', "turn")),
                         response(tool_call("forward", '{"distance_m": 0.2}', "stale")), response())
    monkeypatch.setattr(loop, "describe_scene", Mock(side_effect=["Scene before turn", None]))
    controller = Mock(spec=RoboMasterController)
    controller.get_chassis_state.return_value = {}
    controller.turn.return_value = {"status": "completed"}
    state = RobotState()

    async def two_cycles():
        await loop.run_episode(state, controller)
        await loop.run_episode(state, controller)

    asyncio.run(two_cycles())
    controller.forward.assert_not_called()
    assert state.last_action_result["name"] == "turn"
    assert state.last_action_result["result"]["status"] == "completed"
    planner.client.send_message.assert_awaited_once()
    planner.client.submit_tool_outputs_simple.assert_not_awaited()
    assert planner._pending_tool_outputs  # Submit only after vision recovers.
    assert not state.scene_fresh


@pytest.mark.parametrize("bad_call", [
    tool_call("turn", "{bad json", "bad"),
    tool_call("turn", "[]", "bad"),
    {"id": "bad", "function": None},
    {"id": "bad", "function": {"name": []}},
])
def test_malformed_raw_tool_calls_recover_without_sdk_parsing_crash(bad_call, monkeypatch):
    planner = mock_brain(monkeypatch, response(bad_call), response())
    controller = Mock(spec=RoboMasterController)
    controller.get_chassis_state.return_value = {}

    state = asyncio.run(loop.run_episode(RobotState(), controller))

    assert state.last_action_result["result"]["status"] == "rejected"
    assert [call for call in controller.mock_calls if call[0] in PHYSICAL_ACTIONS] == []
    feedback = planner.client.submit_tool_outputs_simple.call_args.kwargs["tool_outputs"]
    assert json.loads(feedback[0]["output"])["status"] == "rejected"


def test_parser_fast_path_uses_same_validation(monkeypatch):
    mock_brain(monkeypatch, response())
    monkeypatch.setattr(loop.command_parser, "parse", lambda _: {"verb": "turn", "args": {"angle": 30}})
    controller = Mock(spec=RoboMasterController)

    state = asyncio.run(loop.run_episode(RobotState(last_user_command="turn"), controller))

    assert state.last_action_result["result"]["status"] == "rejected"
    assert controller.mock_calls == []
