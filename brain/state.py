from dataclasses import dataclass, field


@dataclass
class RobotState:
    scene_description: str | None = None
    current_goal: str | None = None
    last_user_command: str | None = None
    last_action_result: dict | None = None
    scene_fresh: bool = False
    finished_goal: str | None = None
    search_active: bool = False
    search_direction: int = 0  # +1 left, -1 right; zero when inactive.
    search_rotation_deg: float = 0.0
    search_goal: str | None = None
    recent_observations: list[str] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)
    last_actions: list[dict] = field(default_factory=list)
    mission_context: list[str] = field(default_factory=list)
    memory_goal: str | None = None
    last_frame_at: float = 0.0
    successful_cycles: int = 0
    consecutive_failures: int = 0
    retry_at: float = 0.0
