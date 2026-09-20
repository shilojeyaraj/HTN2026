"""Planner state stays in the per-step message, never in indexed documents."""

import json

from brain import loop
from brain.state import RobotState


class FakeController:
    def get_chassis_state(self):
        return {"position_m": (1.0, 2.0, 90.0)}


def test_planner_receives_dynamic_state_in_its_message(monkeypatch):
    captured = {}
    state = RobotState(
        scene_description="Clear path to the left.",
        current_goal="Find the red chair.",
        last_user_command="Please look left.",
        last_action_result={"name": "turn", "result": {"status": "completed"}},
    )

    monkeypatch.setattr(loop, "_perceive", lambda state, controller: state)
    monkeypatch.setattr(loop.command_parser, "parse", lambda command: None)

    def run_tools(**kwargs):
        captured.update(kwargs)
        return [{"name": "turn", "arguments": {"degrees": 30}, "result": {"status": "completed"}}]

    monkeypatch.setattr(loop.brain, "run_tools", run_tools)

    result = loop.run_episode(state, FakeController())

    assert json.loads(captured["content"]) == {
        "scene_description": "Clear path to the left.",
        "robot_pose": {"position_m": [1.0, 2.0, 90.0]},
        "recent_transcript": "Please look left.",
        "current_goal": "Find the red chair.",
        "prior_action_result": {"name": "turn", "result": {"status": "completed"}},
    }
    assert result.last_action_result == {"name": "turn", "arguments": {"degrees": 30}, "result": {"status": "completed"}}
