from dataclasses import dataclass


@dataclass
class RobotState:
    scene_description: str | None = None
    current_goal: str | None = None
    last_user_command: str | None = None
    last_action_result: dict | None = None
    scene_fresh: bool = False
    finished_goal: str | None = None
