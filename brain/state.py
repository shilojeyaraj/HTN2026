from dataclasses import dataclass, field
from typing import Literal, TypedDict


class Detection(TypedDict):
    label: str
    bbox: tuple[float, float, float, float]
    distance_m: float
    bearing_deg: float


@dataclass
class RobotState:
    timestamp: float = 0.0
    robot_pose: tuple[float, float, float] = (0.0, 0.0, 0.0)  # x, y, heading
    velocity: tuple[float, float] = (0.0, 0.0)  # linear, angular
    detections: list[Detection] = field(default_factory=list)
    scene_description: str | None = None
    current_goal: tuple[float, float] | None = None
    last_user_command: str | None = None
    safety_status: Literal["OK", "VETO"] = "OK"
