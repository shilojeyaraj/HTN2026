from dataclasses import dataclass


@dataclass
class RobotState:
    scene_description: str | None = None
    current_goal: str | None = None
    last_user_command: str | None = None
