"""Deliberative episode: scene understanding -> Backboard planner (verb tools) -> safety
gate -> execution, with real per-verb results fed back to Backboard (Inner Monologue,
CLAUDE.md section 7). Replaces the earlier LangGraph-based graph.py + planner.py now that
Backboard's own thread/tool-calling already provides the orchestration a graph library
would otherwise stand in for.
"""

import logging

from brain import safety
from brain.backboard_client import brain
from brain.state import RobotState
from brain.tools import SYSTEM_PROMPT, VERBS
from control.controller import execute_verb
from perception.camera import get_latest_detections, get_latest_frame
from perception.finetuned_vision import classify_frame
from perception.vision import describe_scene
from voice.tts import speak

logger = logging.getLogger(__name__)


def _perceive(state: RobotState) -> RobotState:
    try:
        frame_jpeg, detections = get_latest_frame()
        state.detections = detections
        state.scene_description = describe_scene(frame_jpeg, detections)
    except Exception:
        logger.warning("vision failed, keeping prior scene_description", exc_info=True)

    try:
        frame_jpeg, _ = get_latest_frame()
        state.venue_model_output = classify_frame(frame_jpeg)
    except Exception:
        logger.warning("finetuned vision failed, no Baseten output this episode", exc_info=True)

    return state


def run_episode(state: RobotState, arbiter) -> RobotState:
    state = _perceive(state)

    def execute_tool(name: str, args: dict) -> dict:
        if name == "speak":
            speak(args["text"])
            return {"status": "completed"}
        if name == "get_obstacles":
            return {"detections": get_latest_detections()}
        if name == "get_state":
            return {"pose": state.robot_pose, "velocity": state.velocity, "goal": state.current_goal}

        # SayCan-style feasibility gate on live detections, not the episode-start snapshot
        # in state.detections, since the world can change mid-episode.
        state.safety_status = safety.check(name, args, get_latest_detections())
        if state.safety_status == "VETO":
            return {"status": "vetoed", "reason": "obstacle ahead"}

        return execute_verb(name, args, arbiter, get_latest_detections)

    user_content = (
        f"Scene: {state.scene_description}\n"
        f"Venue model output: {state.venue_model_output}\n"
        f"Current goal: {state.current_goal}\n"
        f"User command: {state.last_user_command}\n"
        f"Pose: {state.robot_pose}"
    )

    brain.run_tools(
        content=user_content,
        system_prompt=SYSTEM_PROMPT,
        tools=VERBS,
        execute_tool=execute_tool,
        memory="Auto",
    )

    return state
