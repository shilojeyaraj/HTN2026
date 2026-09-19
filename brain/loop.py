"""Deliberative episode: scene understanding -> Backboard planner (verb tools) -> safety
gate -> execution, with real per-verb results fed back to Backboard (Inner Monologue,
CLAUDE.md section 7). Replaces the earlier LangGraph-based graph.py + planner.py now that
Backboard's own thread/tool-calling already provides the orchestration a graph library
would otherwise stand in for.

A Baseten-deployed fine-tuned command parser (brain/command_parser.py) sits between STT
and the brain: simple voice commands ("forward 2 meters", "turn left", "stop") are parsed
and executed directly without a cloud round-trip to Backboard. Complex or unrecognized
commands fall through to the Backboard brain for full reasoning.
"""

import logging

from brain import command_parser, safety
from brain.backboard_client import brain
from brain.state import RobotState
from brain.tools import SYSTEM_PROMPT, VERBS
from control.controller import execute_verb
from perception import sensors
from perception.camera import get_latest_detections, get_latest_frame
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

    return state


def _execute_verb(name: str, args: dict, state: RobotState, arbiter) -> dict:
    """Execute a single verb through the safety gate and controller."""
    if name == "speak":
        speak(args["text"])
        return {"status": "completed"}
    if name == "get_obstacles":
        return {"detections": get_latest_detections()}
    if name == "get_state":
        return {"pose": state.robot_pose, "velocity": state.velocity, "goal": state.current_goal}
    if name == "get_temperature":
        return sensors.read_temperature()
    if name == "get_audio":
        return sensors.read_audio()
    if name == "get_gyro":
        return sensors.read_gyro()

    state.safety_status = safety.check(name, args, get_latest_detections())
    if state.safety_status == "VETO":
        return {"status": "vetoed", "reason": "obstacle ahead"}

    return execute_verb(name, args, arbiter, get_latest_detections)


def run_episode(state: RobotState, arbiter) -> RobotState:
    state = _perceive(state)

    # Fast path: try the Baseten fine-tuned parser for simple voice commands.
    # Falls through to the Backboard brain for complex/unrecognized commands.
    if state.last_user_command:
        parsed = command_parser.parse(state.last_user_command)
        if parsed is not None:
            result = _execute_verb(parsed["verb"], parsed["args"], state, arbiter)
            logger.info("parser fast-path: %s -> %s -> %s", state.last_user_command, parsed, result)
            state.last_user_command = None
            return state

    def execute_tool(name: str, args: dict) -> dict:
        return _execute_verb(name, args, state, arbiter)

    user_content = (
        f"Scene: {state.scene_description}\n"
        f"Current goal: {state.current_goal}\n"
        f"User command: {state.last_user_command}\n"
        f"Pose: {state.robot_pose}"
    )
    state.last_user_command = None  # consume it -- act on a spoken command exactly once

    brain.run_tools(
        content=user_content,
        system_prompt=SYSTEM_PROMPT,
        tools=VERBS,
        execute_tool=execute_tool,
        memory="Auto",
    )

    return state
