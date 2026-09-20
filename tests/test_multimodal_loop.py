"""One image decision per fresh frame; physical hardware and cloud APIs are mocked."""

import asyncio
import json
import logging
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from brain import loop
from brain.backboard_client import BackboardBrain
from brain.state import RobotState
from brain.tools import PHYSICAL_ACTIONS
from control.robomaster import RoboMasterController, RoboMasterError
from perception import vision
from shared.inference import InferenceUnavailable


def decision(tool="turn", args=None, **extra):
    return json.dumps({"observation": "Red chair is to the left.", "tool": tool,
                       "args": {"degrees": 45} if args is None else args,
                       "goal_complete": False, "finding": None, **extra})


@pytest.fixture
def setup_loop(monkeypatch):
    controller = Mock(spec=RoboMasterController)
    controller.get_chassis_state.return_value = {"position_m": (1, 2, 0)}
    controller.get_camera_state.side_effect = lambda: {"last_frame_monotonic_s": time.monotonic(), "frame_age_s": 0.01}
    for name in PHYSICAL_ACTIONS | {"stop"}:
        getattr(controller, name).return_value = {"status": "completed"}
    camera = Mock(return_value=b"jpeg")
    model = AsyncMock(return_value=decision())
    memory = SimpleNamespace(enqueue_memory=Mock(), run_tools=AsyncMock())
    monkeypatch.setattr(loop, "get_latest_frame", camera)
    monkeypatch.setattr(loop, "decide_action", model)
    monkeypatch.setattr(loop, "brain", memory)
    return controller, camera, model, memory


def test_find_chair_uses_one_multimodal_call_with_local_state(setup_loop, caplog):
    controller, camera, model, memory = setup_loop
    state = RobotState(current_goal="find the red chair", last_user_command="Look near the doorway",
                       recent_observations=["A doorway on the left"], findings=[{"type": "hazard", "description": "Debris"}],
                       mission_context=["Search the ground floor"])
    with caplog.at_level(logging.INFO):
        asyncio.run(loop.run_episode(state, controller))
    model.assert_awaited_once()
    jpeg, context = model.call_args.args
    assert jpeg == b"jpeg" and context["current_goal"] == "find the red chair"
    assert context["robot_pose"] == {"position_m": (1, 2, 0)}
    assert context["recent_transcript"] == "Look near the doorway"
    assert context["mission_context"] == ["Search the ground floor"]
    controller.turn.assert_called_once_with(degrees=45)
    memory.run_tools.assert_not_awaited()
    assert not state.scene_fresh and state.retry_at == 0
    for field in ["frame_age_s=", "inference_latency_s=", "observation=", "selected tool=turn", "goal_complete=False", "executor_duration_s="]:
        assert field in caplog.text


@pytest.mark.parametrize("raw", [
    "not JSON", "[]", '{"tool":"turn","args":{"degrees":45}}',
    decision(args={"angle": 45}), decision(args={"degrees": "NaN"}),
    decision(tool="drive_speed", args={}), decision(args={"degrees": 20, "direct": True}),
    decision(goal_complete="false"), decision(goal_complete=True),
    decision(tool=None, args={"degrees": 45}),
    decision(finding={"type": "hazard"}), decision(observation=""),
    decision(actions=[{"tool": "forward"}]),
])
def test_malformed_response_never_moves_and_logs_raw(raw, setup_loop, caplog):
    controller, _, model, _ = setup_loop
    model.return_value = raw
    old = {"name": "stop", "result": {"status": "completed"}}
    state = RobotState(current_goal="find the chair", scene_description="Previous scene", last_action_result=old)
    with caplog.at_level(logging.ERROR):
        asyncio.run(loop.run_episode(state, controller))
    assert not [c for c in controller.mock_calls if c[0] in PHYSICAL_ACTIONS]
    assert "malformed response=" in caplog.text and repr(raw) in caplog.text
    assert state.last_action_result is old and state.scene_description == "Previous scene"
    assert not state.scene_fresh and state.retry_at > time.monotonic()


def test_model_failure_preserves_state_and_defers_without_moving(setup_loop):
    controller, camera, model, _ = setup_loop
    model.side_effect = RuntimeError("provider temporarily unavailable")
    state = RobotState(current_goal="find the chair", recent_observations=["Previous"], last_user_command="look left")
    async def run():
        await loop.run_episode(state, controller)
        await loop.run_episode(state, controller)  # Backoff suppresses calls, not just main.py sleeps.
    asyncio.run(run())
    assert state.recent_observations == ["Previous"] and state.last_user_command == "look left"
    assert camera.call_count == model.await_count == 1
    assert not [c for c in controller.mock_calls if c[0] in PHYSICAL_ACTIONS]


@pytest.mark.parametrize("tool,args", [
    ("forward", {"distance_m": 5}), ("backward", {"distance_m": 0.2}),
    ("strafe_left", {"distance_m": 0.2}), ("strafe_right", {"distance_m": 0.2}),
    ("turn", {"degrees": -300}), ("move_arm", {"x_mm": 100, "y_mm": -100}),
    ("recenter_arm", {}), ("open_gripper", {}), ("close_gripper", {}),
])
def test_valid_response_executes_exactly_one_validated_physical_action(tool, args, setup_loop):
    controller, _, model, _ = setup_loop
    model.return_value = decision(tool, args)
    state = asyncio.run(loop.run_episode(RobotState(current_goal="explore"), controller))
    calls = [c for c in controller.mock_calls if c[0] in PHYSICAL_ACTIONS]
    assert len(calls) == 1 and calls[0][0] == tool
    assert not state.scene_fresh
    if tool == "forward": controller.forward.assert_called_once_with(0.75)
    if tool == "turn": controller.turn.assert_called_once_with(degrees=-90)
    if tool == "move_arm": controller.move_arm.assert_called_once_with(x_mm=80, y_mm=-80)


def test_next_action_requires_a_frame_received_after_motion(setup_loop):
    controller, camera, model, _ = setup_loop
    frame_at = time.monotonic()
    controller.get_camera_state.side_effect = None
    controller.get_camera_state.return_value = {"last_frame_monotonic_s": frame_at, "frame_age_s": 0.1}
    state = RobotState(current_goal="explore")
    async def run():
        await loop.run_episode(state, controller)
        await loop.run_episode(state, controller)
        model.assert_awaited_once()
        controller.get_camera_state.return_value["last_frame_monotonic_s"] = time.monotonic()
        state.retry_at = 0
        await loop.run_episode(state, controller)
    asyncio.run(run())
    assert camera.call_count == 3 and model.await_count == 2 and controller.turn.call_count == 2


def test_goal_complete_terminates_without_executing_an_action(setup_loop):
    controller, _, model, memory = setup_loop
    model.return_value = decision(None, {}, goal_complete=True)
    state = RobotState(current_goal="find the red chair")
    async def run():
        await loop.run_episode(state, controller)
        await loop.run_episode(state, controller)
    asyncio.run(run())
    assert state.finished_goal == state.current_goal
    assert not [c for c in controller.mock_calls if c[0] in PHYSICAL_ACTIONS | {"stop"}]
    model.assert_awaited_once()
    assert memory.enqueue_memory.call_args.args[0] == "mission_summary"


def test_findings_persist_in_background_without_delaying_action(setup_loop, monkeypatch):
    controller, _, model, _ = setup_loop
    finding = {"type": "hazard", "description": "Debris near doorway"}
    model.return_value = decision(finding=finding)
    memory = BackboardBrain("google", "unused")
    memory.client = SimpleNamespace(aclose=AsyncMock())
    release = asyncio.Event()
    writes = []
    async def write(kind, text):
        writes.append((kind, text))
        await release.wait()
    monkeypatch.setattr(memory, "log_finding", write)
    monkeypatch.setattr(loop, "brain", memory)
    state = RobotState(current_goal="explore")
    async def run():
        try:
            await asyncio.wait_for(loop.run_episode(state, controller), timeout=0.5)
            controller.turn.assert_called_once()
            await asyncio.sleep(0)  # Let the background worker reach the fake network wait.
            assert not release.is_set() and not memory._memory_task.done()
            assert state.findings == [finding]
        finally:
            release.set()
            await memory.aclose()
    asyncio.run(run())
    assert [kind for kind, _ in writes] == ["mission_context", "hazard"]
    assert json.loads(writes[-1][1])["finding"] == finding
    assert memory.client is None


def test_transient_backoff_is_bounded_and_retry_after_is_respected(setup_loop):
    controller, _, model, _ = setup_loop
    model.side_effect = RuntimeError("429 RESOURCE_EXHAUSTED retryDelay: 44s")
    state = RobotState(current_goal="explore")
    async def run():
        for attempt in range(loop.MAX_MODEL_FAILURES):
            state.retry_at = 0
            await loop.run_episode(state, controller)
            assert state.retry_at - time.monotonic() >= 44
        state.retry_at = 0
        with pytest.raises(InferenceUnavailable):
            await loop.run_episode(state, controller)
    asyncio.run(run())
    controller.turn.assert_not_called()


def test_hardware_failure_consumes_view_and_never_chains_motion(setup_loop):
    controller, _, _, _ = setup_loop
    controller.turn.side_effect = RoboMasterError("link lost")
    state = asyncio.run(loop.run_episode(RobotState(current_goal="explore"), controller))
    assert state.last_action_result["result"]["status"] == "error"
    assert not state.scene_fresh
    controller.forward.assert_not_called()


def test_multimodal_sdk_request_uses_jpeg_context_schema_and_shared_client(monkeypatch):
    from brain.tools import DECISION_SCHEMA, RESCUE_PROTOCOLS
    generate = AsyncMock(return_value=SimpleNamespace(text=decision()))
    client = SimpleNamespace(aio=SimpleNamespace(models=SimpleNamespace(generate_content=generate), aclose=AsyncMock()), close=Mock())
    monkeypatch.setattr(vision, "_client", client)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    async def run():
        for _ in range(2):
            assert await vision.decide_action(b"jpeg", {"current_goal": "find chair"}) == decision()
        client.close.assert_not_called()
        client.aio.aclose.assert_not_awaited()
        await vision.aclose_vision_client()
    asyncio.run(run())
    request = generate.call_args.kwargs
    assert request["model"] == vision.ACTION_MODEL
    assert request["contents"][0].inline_data.data == b"jpeg"
    assert json.loads(request["contents"][1])["allowed_tools"]
    assert request["config"]["response_json_schema"] == DECISION_SCHEMA
    assert RESCUE_PROTOCOLS in request["config"]["system_instruction"]
    client.aio.aclose.assert_awaited_once()
    client.close.assert_called_once()


def test_real_gemini_sdk_serializes_the_structured_request_offline(monkeypatch):
    import httpx
    from google import genai
    from brain.tools import DECISION_SCHEMA
    requests = []
    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [{"text": decision()}]},
                                                        "finishReason": "STOP"}]})
    async def run():
        transport = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        client = genai.Client(api_key="offline-test", http_options={"httpx_async_client": transport})
        monkeypatch.setattr(vision, "_client", client)
        monkeypatch.setenv("GEMINI_API_KEY", "offline-test")
        try:
            assert await vision.decide_action(b"jpeg", {"current_goal": "find chair"}) == decision()
            assert requests[0]["generationConfig"]["responseJsonSchema"] == DECISION_SCHEMA
            assert requests[0]["contents"][0]["parts"][0]["inlineData"]["mimeType"] == "image/jpeg"
        finally:
            await vision.aclose_vision_client()
    asyncio.run(run())
