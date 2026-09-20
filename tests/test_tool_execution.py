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
@pytest.mark.parametrize("value,expected", [("2.5", 0.75), (0.01, 0.05), ("0.2", 0.2), (0.6, 0.6), (0.75, 0.75)])
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
    controller.turn.assert_called_once_with(degrees=-90)
    loop._execute_verb("move_arm", {"x_mm": "100", "y_mm": -200}, RobotState(scene_fresh=True), controller)
    controller.move_arm.assert_called_once_with(x_mm=80, y_mm=-80)
    loop._execute_verb("speak", {"text": "x" * 300}, RobotState(), controller)
    speech.assert_called_once_with("x" * 240)
    assert validate_tool_args("turn", {"degrees": 200}) == {"degrees": 90}


def test_schema_bounds_match_execution_limits():
    for name, schema in TOOL_PARAMETERS.items():
        assert schema["additionalProperties"] is False
        for key, bounds in {"distance_m": (0.05, 0.75), "degrees": (-90, 90), "x_mm": (-80, 80), "y_mm": (-80, 80)}.items():
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


@pytest.mark.parametrize("bad_call", [
    tool_call("turn", "{bad json", "bad"), tool_call("turn", "[]", "bad"),
    {"id": "bad", "function": None}, {"id": "bad", "function": {"name": []}},
])
def test_optional_backboard_planner_still_rejects_malformed_calls(bad_call):
    planner = BackboardBrain("google", "test-model")
    planner.assistant_id = "assistant"
    planner.client = SimpleNamespace(send_message=AsyncMock(return_value=response(bad_call)),
                                    submit_tool_outputs_simple=AsyncMock(return_value=response()))
    controller = Mock(spec=RoboMasterController)
    state = RobotState(scene_fresh=True)
    results = asyncio.run(planner.run_tools("scene", "prompt", [],
                          lambda name, args: loop._execute_verb(name, args, state, controller)))
    assert results[0]["result"]["status"] == "rejected"
    assert controller.mock_calls == []


def test_planner_cannot_request_the_direct_mode_bypass():
    controller = Mock(spec=RoboMasterController)
    result = loop._execute_verb("turn", {"degrees": 90, "direct": True}, RobotState(), controller)
    assert result["status"] == "rejected"
    assert controller.mock_calls == []
