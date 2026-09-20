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
import math
import time

from brain import command_parser, safety
from brain.backboard_client import brain
from brain.state import RobotState
from brain.tools import SYSTEM_PROMPT, VERBS
from control.controller import execute_verb
from control.telemetry import BrainActivity, SensorState, MissionInsights
from perception import sensors
from perception.camera import get_latest_detections, get_latest_frame
from perception.vision import describe_scene
from tracking import mongo as db
from voice.tts import speak

logger = logging.getLogger(__name__)

brain_activity = BrainActivity()
sensor_state = SensorState()
mission_insights = MissionInsights()

# Rate limiting: the brain only calls Backboard when an event triggers.
# This prevents burning API credits on every 1-second tick when nothing changes.
MIN_BRAIN_GAP_S = 10.0  # minimum seconds between brain calls unless an event triggers
OBSTACLE_CLOSE_M = 0.5    # obstacle within this distance triggers brain
TEMP_THRESHOLD_C = 40.0   # temperature above this triggers brain
AUDIO_EVENT_DB = 70.0      # audio above this triggers brain

_last_brain_call_ts = 0.0
_last_pose = (0.0, 0.0, 0.0)


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
        brain_activity.log_call(name, args, {"status": "completed"})
        db.log_brain_call(name, args, {"status": "completed"}, state.robot_pose)
        return {"status": "completed"}
    if name == "look_around":
        try:
            frame_jpeg, detections = get_latest_frame()
            state.scene_description = describe_scene(frame_jpeg, detections)
            result = {"scene": state.scene_description}
            brain_activity.log_call(name, args, result)
            db.log_brain_call(name, args, result, state.robot_pose)
            return result
        except Exception:
            result = {"error": "vision unavailable", "scene": state.scene_description or "unknown"}
            brain_activity.log_call(name, args, result)
            db.log_brain_call(name, args, result, state.robot_pose)
            return result
    if name == "check_map":
        if mapper is not None:
            result = mapper.nearby_summary(state.robot_pose, args.get("radius_m", 3.0))
            brain_activity.log_call(name, args, result)
            db.log_brain_call(name, args, result, state.robot_pose)
            return result
        result = {"error": "map not available"}
        brain_activity.log_call(name, args, result)
        db.log_brain_call(name, args, result, state.robot_pose)
        return result
    if name == "check_safety":
        result_val = safety.check(args["action"], args, get_latest_detections())
        result = {"status": result_val, "action": args["action"]}
        brain_activity.log_call(name, args, result)
        db.log_brain_call(name, args, result, state.robot_pose)
        return result
    if name == "search_knowledge":
        result = brain.search_memory(args["query"])
        brain_activity.log_call(name, args, result or {"results": "no results"})
        db.log_rag(args["query"], result or {"results": "no results"}, state.robot_pose)
        db.log_brain_call(name, args, result or {"results": "no results"}, state.robot_pose)
        return result or {"results": "no results"}
    if name == "log_finding":
        result = brain.log_finding(args["finding_type"], args["description"])
        brain_activity.log_call(name, args, result or {"status": "logged"})
        db.log_finding(args["finding_type"], args["description"], state.robot_pose)
        db.log_brain_call(name, args, result or {"status": "logged"}, state.robot_pose)
        return result or {"status": "logged"}
    if name == "analyze_patterns":
        result = brain.get_insights()
        if result:
            mission_insights.update(result)
            db.log_insights(result)
        brain_activity.log_call(name, args, result or {"insights": "no data"})
        db.log_brain_call(name, args, result or {"insights": "no data"}, state.robot_pose)
        return result or {"insights": "no data"}
    if name == "get_obstacles":
        result = {"detections": get_latest_detections()}
        brain_activity.log_call(name, args, result)
        db.log_brain_call(name, args, result, state.robot_pose)
        return result
    if name == "get_state":
        result = {"pose": state.robot_pose, "velocity": state.velocity, "goal": state.current_goal}
        brain_activity.log_call(name, args, result)
        db.log_brain_call(name, args, result, state.robot_pose)
        return result
    if name == "get_temperature":
        temp = sensors.read_temperature()
        sensor_state.update_temperature(temp["celsius"], temp["status"])
        brain_activity.log_call(name, args, temp)
        db.log_brain_call(name, args, temp, state.robot_pose)
        db.log_sensor_reading(temp, sensors.read_audio(), sensors.read_gyro(), state.robot_pose)
        return temp
    if name == "get_audio":
        audio = sensors.read_audio()
        sensor_state.update_audio(audio.get("db", 0), audio.get("event"))
        brain_activity.log_call(name, args, audio)
        db.log_brain_call(name, args, audio, state.robot_pose)
        return audio
    if name == "get_gyro":
        gyro = sensors.read_gyro()
        sensor_state.update_gyro(gyro.get("pitch_deg", 0), gyro.get("roll_deg", 0),
                                 gyro.get("tipped", False), gyro.get("bump", False))
        brain_activity.log_call(name, args, gyro)
        db.log_brain_call(name, args, gyro, state.robot_pose)
        return gyro

    state.safety_status = safety.check(name, args, get_latest_detections())
    if state.safety_status == "VETO":
        result = {"status": "vetoed", "reason": "obstacle ahead"}
        brain_activity.log_call(name, args, result)
        db.log_brain_call(name, args, result, state.robot_pose)
        return result

    result = execute_verb(name, args, arbiter, get_latest_detections)
    brain_activity.log_call(name, args, result)
    db.log_brain_call(name, args, result, state.robot_pose)
    return result


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


def _should_call_brain(state: RobotState, transcript_buffer) -> tuple[bool, str]:
    """Check if an event warrants a Backboard brain call. Returns (should_call, reason)."""
    global _last_brain_call_ts, _last_pose
    now = time.time()

    # Event 1: new transcript (someone spoke)
    if state.last_user_command:
        return True, "voice command received"

    # Event 2: check transcripts buffer for new final transcripts
    if transcript_buffer is not None:
        text = transcript_buffer.consume_final()
        if text:
            state.last_user_command = text
            logger.info("transcript -> last_user_command: %s", text)
            db.log_transcript(text, final=True, utterance_id=0, pose=state.robot_pose)
            return True, "new transcript"

    # Event 3: obstacle detected close ahead
    dets = get_latest_detections()
    close = [d for d in dets if abs(d["bearing_deg"]) < 30 and d["distance_m"] < OBSTACLE_CLOSE_M]
    if close:
        return True, f"obstacle at {close[0]['distance_m']:.1f}m"

    # Event 4: sensor threshold crossed
    temp = sensors.read_temperature()
    if temp["celsius"] >= TEMP_THRESHOLD_C:
        return True, f"temperature {temp['celsius']}°C"

    audio = sensors.read_audio()
    if audio.get("db", 0) >= AUDIO_EVENT_DB or audio.get("event"):
        return True, f"audio event: {audio.get('event', {}).get('kind', 'loud')}"

    gyro = sensors.read_gyro()
    if gyro.get("tipped") or gyro.get("bump"):
        return True, f"gyro: tipped={gyro.get('tipped')}, bump={gyro.get('bump')}"

    # Event 5: rover has moved significantly since last brain call
    pose = state.robot_pose
    moved = math.sqrt((pose[0] - _last_pose[0])**2 + (pose[1] - _last_pose[1])**2)
    if moved > 2.0 and (now - _last_brain_call_ts) >= MIN_BRAIN_GAP_S:
        return True, f"moved {moved:.1f}m, {now - _last_brain_call_ts:.0f}s since last call"

    # Event 6: minimum time gap with no events (periodic check-in)
    if (now - _last_brain_call_ts) >= MIN_BRAIN_GAP_S * 3:
        return True, "periodic check-in (30s)"

    return False, "no event"


def run_episode(state: RobotState, arbiter, mapper=None, pose_estimator=None,
                transcript_buffer=None) -> RobotState:
    global _last_brain_call_ts, _last_pose
    state = _perceive(state)

    # Check for new transcripts (always, even if brain doesn't call)
    if transcript_buffer is not None and not state.last_user_command:
        text = transcript_buffer.consume_final()
        if text:
            state.last_user_command = text
            logger.info("transcript -> last_user_command: %s", text)
            db.log_transcript(text, final=True, utterance_id=0, pose=state.robot_pose)

    # Fast path: try the Baseten fine-tuned parser for simple voice commands.
    # Always active — no rate limiting on the parser.
    if state.last_user_command:
        parsed = command_parser.parse(state.last_user_command)
        if parsed is not None:
            result = _execute_verb(parsed["verb"], parsed["args"], state, arbiter, mapper)
            logger.info("parser fast-path: %s -> %s -> %s", state.last_user_command, parsed, result)
            state.last_user_command = None
            _update_map(state, mapper, pose_estimator, transcript_buffer)
            return state

    # Event-driven brain: only call Backboard when something significant happens
    should_call, reason = _should_call_brain(state, transcript_buffer)

    if not should_call:
        # No event — just update the map and return
        _update_map(state, mapper, pose_estimator, transcript_buffer)
        return state

    logger.info("brain call triggered: %s", reason)

    def execute_tool(name: str, args: dict) -> dict:
        return _execute_verb(name, args, state, arbiter, mapper)

    user_content = (
        f"Scene: {state.scene_description}\n"
        f"Current goal: {state.current_goal}\n"
        f"User command: {state.last_user_command}\n"
        f"Pose: {state.robot_pose}\n"
        f"Trigger: {reason}"
    )
    state.last_user_command = None  # consume it -- act on a spoken command exactly once

    brain.run_tools(
        content=user_content,
        system_prompt=SYSTEM_PROMPT,
        tools=VERBS,
        execute_tool=execute_tool,
        memory="Auto",
    )

    _last_brain_call_ts = time.time()
    _last_pose = state.robot_pose

    _update_map(state, mapper, pose_estimator, transcript_buffer)
    return state
