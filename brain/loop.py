"""Deliberative episode: scene understanding -> Backboard planner (verb tools) -> safety
gate -> execution, with real per-verb results fed back to Backboard (Inner Monologue,
CLAUDE.md section 7). Replaces the earlier LangGraph-based graph.py + planner.py now that
Backboard's own thread/tool-calling already provides the orchestration a graph library
would otherwise stand in for.

A Baseten-deployed fine-tuned command parser (brain/command_parser.py) sits between STT
and the brain: simple voice commands ("forward 2 meters", "turn left", "stop") are parsed
and executed directly without a cloud round-trip to Backboard. Complex or unrecognized
commands fall through to the Backboard brain for full reasoning.

After each episode, sensor readings are fed into the occupancy map (control/mapper.py)
so the frontend can render a live area map.
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


def _execute_verb(name: str, args: dict, state: RobotState, arbiter, mapper=None) -> dict:
    """Execute a single verb through the safety gate and controller."""
    if name == "speak":
        speak(args["text"])
        return {"status": "completed"}
    if name == "look_around":
        try:
            frame_jpeg, detections = get_latest_frame()
            state.scene_description = describe_scene(frame_jpeg, detections)
            return {"scene": state.scene_description}
        except Exception:
            return {"error": "vision unavailable", "scene": state.scene_description or "unknown"}
    if name == "check_map":
        if mapper is not None:
            return mapper.nearby_summary(state.robot_pose, args.get("radius_m", 3.0))
        return {"error": "map not available"}
    if name == "check_safety":
        result = safety.check(args["action"], args, get_latest_detections())
        return {"status": result, "action": args["action"]}
    if name == "search_knowledge":
        return brain.search_memory(args["query"])
    if name == "log_finding":
        return brain.log_finding(args["finding_type"], args["description"])
    if name == "analyze_patterns":
        return brain.get_insights()
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


def _update_map(state: RobotState, mapper, pose_estimator, transcript_buffer=None) -> None:
    """Feed the latest sensor readings into the occupancy map after each episode."""
    if mapper is None or pose_estimator is None:
        return
    pose = pose_estimator.pose
    mapper.add_trail(pose)

    for det in state.detections:
        if det["label"] == "obstacle":
            proximity = max(0.0, 1.0 - det["distance_m"])
            mapper.add_depth(pose, det["bearing_deg"], proximity)

    if transcript_buffer is not None:
        for event in transcript_buffer.recent(3):
            mapper.add_transcript(pose, event.text, event.final)

    audio = sensors.read_audio()
    if audio.get("event"):
        ev = audio["event"]
        mapper.add_sound(pose, ev["kind"], ev.get("label", ev["kind"]), audio["db"])

    temp = sensors.read_temperature()
    mapper.add_heat(pose, temp["celsius"], temp["status"])

    gyro = sensors.read_gyro()
    if gyro.get("tipped"):
        mapper.add_hazard(pose, "tipped")
    if gyro.get("bump"):
        mapper.add_hazard(pose, "bump")

    if state.scene_description:
        mapper.add_annotation(pose, state.scene_description, "gemini")


def run_episode(state: RobotState, arbiter, mapper=None, pose_estimator=None,
                transcript_buffer=None) -> RobotState:
    state = _perceive(state)

    if transcript_buffer is not None and not state.last_user_command:
        text = transcript_buffer.consume_final()
        if text:
            state.last_user_command = text
            logger.info("transcript -> last_user_command: %s", text)

    # Fast path: try the Baseten fine-tuned parser for simple voice commands.
    # Falls through to the Backboard brain for complex/unrecognized commands.
    if state.last_user_command:
        parsed = command_parser.parse(state.last_user_command)
        if parsed is not None:
            result = _execute_verb(parsed["verb"], parsed["args"], state, arbiter, mapper)
            logger.info("parser fast-path: %s -> %s -> %s", state.last_user_command, parsed, result)
            state.last_user_command = None
            _update_map(state, mapper, pose_estimator, transcript_buffer)
            return state

    def execute_tool(name: str, args: dict) -> dict:
        return _execute_verb(name, args, state, arbiter, mapper)

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

    _update_map(state, mapper, pose_estimator, transcript_buffer)
    return state
