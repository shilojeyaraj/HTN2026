"""Rate limits cannot replay robot actions or silently restart an episode."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, Mock

import httpx
import pytest
from backboard.exceptions import BackboardRateLimitError
from backboard.models import ChatMessagesResponse

from brain import backboard_client, loop
from brain.backboard_client import BackboardBrain
from brain.state import RobotState
from control.robomaster import RoboMasterController
from perception import vision
from shared.inference import InferenceUnavailable, is_daily_quota, retry_delay
from tests.test_tool_execution import response, tool_call
from tests.test_vision import vision_response


DAILY = "LLM Invocation Error: 429 RESOURCE_EXHAUSTED; GenerateRequestsPerDayPerProjectPerModel-FreeTier, limit: 20; retryDelay: 44s"
MINUTE = "LLM Invocation Error: 429 RESOURCE_EXHAUSTED; Please retry in 44.245s; 'retryDelay': '44s'"


def failed(content):
    # Backboard can return HTTP 200 and even COMPLETED with an embedded error.
    return ChatMessagesResponse(messages=[{
        "status": "COMPLETED", "content": content,
        "thread_id": "thread", "assistant_id": "assistant",
    }])


def planner_with(*responses, **kwargs):
    # Optional fallbacks remain testable, but the live app doesn't enable one.
    kwargs.setdefault("fallback_model", "test-fallback")
    planner = BackboardBrain("openai", "gpt-4.1", **kwargs)
    planner.assistant_id = "assistant"
    planner.client = SimpleNamespace(send_message=AsyncMock(side_effect=responses))
    return planner


def test_daily_quota_switches_once_without_sleep_or_reexecuting_tools(monkeypatch):
    planner = planner_with(failed(DAILY), response(), response())
    sleep = AsyncMock()
    monkeypatch.setattr(backboard_client.asyncio, "sleep", sleep)
    execute = Mock()

    async def run():
        await planner.run_tools("same scene", "prompt", [], execute, "Auto")
        await planner.run_tools("next scene", "prompt", [], execute, "Auto")

    asyncio.run(run())
    requests = planner.client.send_message.call_args_list
    assert [r.kwargs["model_name"] for r in requests] == ["gpt-4.1", "test-fallback", "test-fallback"]
    assert requests[0].kwargs["content"] == requests[1].kwargs["content"]
    assert requests[1].kwargs["thread_id"] == "thread"
    assert all(r.kwargs["memory"] == "Auto" for r in requests)
    execute.assert_not_called()
    sleep.assert_not_awaited()


def test_quota_exhaustion_stops_instead_of_starting_more_episodes():
    planner = planner_with(failed(DAILY), failed(DAILY))
    execute = Mock()

    async def run():
        for _ in range(2):
            with pytest.raises(InferenceUnavailable, match="quota"):
                await planner.run_tools("scene", "prompt", [], execute)

    asyncio.run(run())
    assert planner.client.send_message.await_count == 2
    execute.assert_not_called()


def test_http_rate_limit_honors_retry_after_and_preserves_request(monkeypatch):
    error = BackboardRateLimitError("rate limit", 429, httpx.Response(429, headers={"Retry-After": "90"}))
    planner = planner_with(error, response())
    sleep = AsyncMock()
    monkeypatch.setattr(backboard_client.asyncio, "sleep", sleep)
    execute = Mock()
    asyncio.run(planner.run_tools("scene", "prompt", [], execute))
    sleep.assert_awaited_once_with(91)
    assert planner.client.send_message.call_args_list[0] == planner.client.send_message.call_args_list[1]
    execute.assert_not_called()
    assert retry_delay(MINUTE, 0) == 45.245
    assert retry_delay("retryDelay: 90000ms", 0) == 91
    assert is_daily_quota(DAILY) and not is_daily_quota(MINUTE)


def test_http_rejected_tool_outputs_are_retried_without_executing_again(monkeypatch):
    planner = planner_with()
    planner.thread_id = "thread"
    planner._pending_tool_outputs = [{"tool_call_id": "already-executed", "output": '{"status":"completed"}'}]
    planner.client.submit_tool_outputs_simple = AsyncMock(side_effect=[
        BackboardRateLimitError("rate limit", 429), response(),
    ])
    monkeypatch.setattr(backboard_client.asyncio, "sleep", AsyncMock())
    execute = Mock()
    asyncio.run(planner.run_tools("fresh scene", "prompt", [], execute))
    submissions = planner.client.submit_tool_outputs_simple.call_args_list
    assert len(submissions) == 2 and submissions[0] == submissions[1]
    assert planner._pending_tool_outputs is None
    planner.client.send_message.assert_not_awaited()
    execute.assert_not_called()


def test_transient_retries_are_bounded_and_stay_in_one_planner_call(monkeypatch):
    planner = planner_with(*([failed(MINUTE)] * 4), response())
    sleep = AsyncMock()
    monkeypatch.setattr(backboard_client.asyncio, "sleep", sleep)
    asyncio.run(planner.run_tools("one scene", "prompt", [], Mock()))
    assert sleep.await_count == 3
    assert planner.client.send_message.await_count == 5
    assert planner.model_name == "test-fallback"
    assert {r.kwargs["content"] for r in planner.client.send_message.call_args_list} == {"one scene"}


def test_continuation_rate_limit_replans_without_resubmitting_consumed_outputs(monkeypatch):
    planner = planner_with(response(tool_call("turn", '{"degrees": 20}', "first")),
                           response(tool_call("forward", '{"distance_m": 0.2}', "next")))
    planner.client.submit_tool_outputs_simple = AsyncMock(return_value=failed(DAILY))
    monkeypatch.setattr(loop, "brain", planner)
    camera = Mock(return_value=b"jpeg")
    perceive = Mock(side_effect=["Before turn", "After turn"])
    monkeypatch.setattr(loop, "get_latest_frame", camera)
    monkeypatch.setattr(loop, "describe_scene", perceive)
    controller = Mock(spec=RoboMasterController)
    controller.get_chassis_state.return_value = {}
    controller.turn.return_value = controller.forward.return_value = {"status": "completed"}

    async def run():
        state = await loop.run_episode(RobotState(current_goal="Explore"), controller)
        await loop.run_episode(state, controller)

    asyncio.run(run())
    controller.turn.assert_called_once_with(degrees=20)
    controller.forward.assert_called_once_with(0.2)
    planner.client.submit_tool_outputs_simple.assert_awaited_once()
    assert camera.call_count == perceive.call_count == 2
    retry = planner.client.send_message.call_args.kwargs
    assert retry["thread_id"] == "thread"
    assert retry["model_name"] == "test-fallback"
    assert "After turn" in retry["content"] and "Already processed tool results" in retry["content"]
    assert planner._pending_tool_outputs[0]["tool_call_id"] == "next"


@pytest.fixture
def vision_client(monkeypatch):
    client = SimpleNamespace(post=Mock(), close=Mock())
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(vision, "_client", client)
    monkeypatch.setattr(vision, "MODEL", "gpt-4.1")
    monkeypatch.setattr(vision, "MIN_INTERVAL_S", 0)
    monkeypatch.setattr(vision, "_next_request_at", 0)
    monkeypatch.setattr(vision, "_rate_limit_attempt", 0)
    monkeypatch.setattr(vision, "_blocked_reason", None)
    return client


def test_vision_reuses_gpt41_client_for_later_frames(vision_client):
    generate = vision_client.post
    generate.side_effect = [vision_response("Clear floor"), vision_response("New scene")]
    assert vision.describe_scene(b"first jpeg") == "Clear floor"
    assert vision.describe_scene(b"next jpeg") == "New scene"
    assert [r.kwargs["json"]["model"] for r in generate.call_args_list] == ["gpt-4.1", "gpt-4.1"]
    vision_client.close.assert_not_called()
    vision.close_vision_client()
    vision_client.close.assert_called_once()


def test_vision_cooldown_skips_requests_until_a_new_frame_can_be_read(vision_client, monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(vision.time, "monotonic", lambda: clock[0])
    generate = vision_client.post
    generate.side_effect = [httpx.Response(429, headers={"Retry-After": "44"},
                                          request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                                          json={"error": {"code": "rate_limit_exceeded"}}),
                            vision_response("Recovered scene")]
    assert vision.describe_scene(b"old jpeg") is None
    assert vision.describe_scene(b"too soon") is None
    assert generate.call_count == 1
    clock[0] = 146
    assert vision.describe_scene(b"fresh jpeg") == "Recovered scene"
    import base64
    image_url = generate.call_args.kwargs["json"]["input"][0]["content"][1]["image_url"]
    assert base64.b64decode(image_url.split(",", 1)[1]) == b"fresh jpeg"
    assert all(r.kwargs["json"]["model"] == "gpt-4.1" for r in generate.call_args_list)


def test_vision_insufficient_quota_stops_without_switching_models(vision_client):
    generate = vision_client.post
    generate.return_value = httpx.Response(429, request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
                                           json={"error": {"code": "insufficient_quota"}})
    assert vision.describe_scene(b"jpeg") is None
    assert vision.describe_scene(b"jpeg") is None
    assert generate.call_count == 1
    assert "quota exhausted for gpt-4.1" in vision.vision_unavailable_reason()


def test_gpt41_planner_defaults_to_no_model_switch():
    planner = BackboardBrain("openai", "gpt-4.1")
    planner.assistant_id = "assistant"
    planner.client = SimpleNamespace(send_message=AsyncMock(return_value=failed("429 insufficient_quota")))
    with pytest.raises(InferenceUnavailable):
        asyncio.run(planner.run_tools("scene", "prompt", [], Mock()))
    planner.client.send_message.assert_awaited_once()
    assert planner.model_name == "gpt-4.1"
    assert planner._fallback == ("openai", "")


def test_mission_shutdown_stops_robot_and_closes_clients_on_exhaustion(monkeypatch):
    import main

    controller = MagicMock(spec=RoboMasterController)
    controller.__enter__.return_value = controller
    planner = SimpleNamespace(aclose=AsyncMock())
    episode = AsyncMock(side_effect=InferenceUnavailable("daily quota exhausted"))
    close_vision = Mock()
    monkeypatch.setattr("sys.argv", ["main.py", "--goal", "Test"])
    monkeypatch.setattr(main, "RoboMasterController", lambda: controller)
    monkeypatch.setattr(main, "brain", planner)
    monkeypatch.setattr(main, "run_episode", episode)
    monkeypatch.setattr(main, "close_vision_client", close_vision)

    asyncio.run(main.main())

    episode.assert_awaited_once()
    controller.stop.assert_called_once()
    controller.__exit__.assert_called_once()
    planner.aclose.assert_awaited_once()
    close_vision.assert_called_once()
