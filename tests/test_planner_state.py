"""Bounded local context replaces per-step retrieval and indexed documents."""

import asyncio
import time
from unittest.mock import AsyncMock, Mock

from brain import loop
from brain.state import RobotState
from control.robomaster import RoboMasterController
from tests.test_multimodal_loop import decision


def test_local_history_is_bounded_and_summaries_are_occasional(monkeypatch):
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
