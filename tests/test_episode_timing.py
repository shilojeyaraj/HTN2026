"""Successful cycles have no artificial gap; failures alone schedule a sleep."""

import asyncio
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import main
from control.robomaster import RoboMasterController


@pytest.mark.parametrize("retry", [False, True])
def test_main_only_sleeps_for_a_failed_cycle(retry, monkeypatch):
    controller = MagicMock(spec=RoboMasterController)
    controller.__enter__.return_value = controller
    calls = 0
    async def episode(state, _controller):
        nonlocal calls
        calls += 1
        state.retry_at = time.monotonic() + 1 if retry else 0
        if calls == 2:
            state.finished_goal = state.current_goal
        return state
    sleep = AsyncMock()
    monkeypatch.setattr("sys.argv", ["main.py", "--goal", "find the chair"])
    monkeypatch.setattr(main, "RoboMasterController", lambda: controller)
    monkeypatch.setattr(main, "run_episode", episode)
    monkeypatch.setattr(main.asyncio, "sleep", sleep)
    monkeypatch.setattr(main, "brain", SimpleNamespace(aclose=AsyncMock()))
    monkeypatch.setattr(main, "aclose_vision_client", AsyncMock())
    asyncio.run(main.main())
    assert calls == 2 and sleep.await_count == int(retry)
    main.aclose_vision_client.assert_awaited_once()
