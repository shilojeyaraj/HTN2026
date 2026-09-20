from dataclasses import dataclass


@dataclass
class RobotState:
    scene_description: str | None = None
    current_goal: tuple[float, float] | None = None
    last_user_command: str | None = None
