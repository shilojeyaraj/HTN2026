"""Deliberative episode: RoboMaster perception, planning, and bounded tool execution."""

import logging
import math
import json
import re
import time

from brain.backboard_client import brain
from brain.direct_commands import decompose_direct_command, parse_direct_command
from brain.state import RobotState
from brain.tools import PHYSICAL_ACTIONS, validate_decision, validate_tool_args
from control.robomaster import RoboMasterController
from perception.camera import get_latest_frame
from perception.vision import ACTION_MODEL, decide_action
from shared.inference import InferenceUnavailable, is_daily_quota, is_rate_limited, retry_delay
from voice.tts import speak

logger = logging.getLogger(__name__)


MAX_MODEL_FAILURES = 5
MEMORY_SUMMARY_INTERVAL = 10
SEARCH_TURN_DEG = 60.0


def _reset_search(state: RobotState) -> None:
    state.search_active = False
    state.search_direction = 0
    state.search_rotation_deg = 0.0
    state.search_goal = None


def _search_decision(state: RobotState, decision: dict) -> tuple[dict, bool]:
    """Replace unseen-target motion with one scan step; keep explicit safety stops."""
    if decision["target_visible"]:
        logger.info("Search target detected: goal=%r cumulative_deg=%.1f", state.current_goal, state.search_rotation_deg)
        _reset_search(state)
        return decision, False
    if state.search_active and state.search_rotation_deg >= 360:
        # This decision used a fresh frame AFTER the final turn, so the last sector
        # also got inspected before declaring the scan exhausted.
        logger.info("Search full 360 scan completed: target not found goal=%r", state.current_goal)
        _reset_search(state)
        state.finished_goal = state.current_goal  # Do not restart on the next cycle.
        if decision["tool"] == "stop":
            return decision, False
        return {**decision, "goal_complete": False, "tool": "speak", "args": {
            "text": "Target not found after a full 360-degree scan."
        }}, False
    if decision["goal_complete"]:
        raise ValueError("search goal cannot be complete while target_visible=false")
    if decision["tool"] == "stop":
        return decision, False
    if not math.isfinite(SEARCH_TURN_DEG) or SEARCH_TURN_DEG <= 0:
        raise ValueError("SEARCH_TURN_DEG must be finite and positive")
    if not state.search_active:
        state.search_active = True
        state.search_direction = 1  # Choose left once; the model cannot reverse it.
        state.search_rotation_deg = 0.0
        state.search_goal = state.current_goal
        logger.info("Search started: goal=%r direction=left cumulative_deg=0", state.current_goal)
    args = validate_tool_args("turn", {"degrees": state.search_direction * min(
        SEARCH_TURN_DEG, 360 - state.search_rotation_deg,
    )})
    return {**decision, "tool": "turn", "args": args}, True


def _retry_cycle(state: RobotState, error, retry_after=None) -> None:
    state.scene_fresh = False
    if is_daily_quota(error):
        raise InferenceUnavailable(f"Multimodal quota exhausted: {error}")
    state.consecutive_failures += 1
    if state.consecutive_failures > MAX_MODEL_FAILURES:
        raise InferenceUnavailable(f"Multimodal decision failed after {MAX_MODEL_FAILURES} retries: {error}")
    delay = (retry_delay(error, state.consecutive_failures - 1, retry_after) if is_rate_limited(error)
             else min(0.5 * 2 ** (state.consecutive_failures - 1), 8.0))
    state.retry_at = time.monotonic() + delay
    logger.warning("CLOSED_LOOP retry=%d delay_s=%.2f; no action: %s", state.consecutive_failures, delay, error)


def _mission_context(state: RobotState) -> dict:
    return {"current_goal": state.current_goal, "recent_transcript": state.last_user_command,
            "recent_observations": state.recent_observations[-8:], "findings": state.findings[-24:],
            "last_actions": state.last_actions[-8:], "prior_action_result": state.last_action_result,
            "mission_context": state.mission_context[-8:],
            "search_active": state.search_active, "search_direction": state.search_direction,
            "search_rotation_deg": state.search_rotation_deg}


def _execute_verb(name: str, args, state: RobotState, controller: RoboMasterController, *, direct: bool = False) -> dict:
    """Execute a planner tool without exposing the RoboMaster SDK to the planner."""
    logger.info("Executing tool=%s args=%r", name, args)
    try:
        params = validate_tool_args(name, args)
        # Only the local user-command router can opt out of perception. Planner
        # callbacks never pass this flag, and tool schemas cannot supply it.
        if name in PHYSICAL_ACTIONS and not direct and not state.scene_fresh:
            raise ValueError("physical action requires a fresh camera scene")
    except ValueError as exc:
        logger.error("Rejected tool=%s args=%r: %s", name, args, exc)
        return {"status": "rejected", "detail": str(exc)}

    # An attempted motion can change the view even if the hardware reports an error.
    if name in PHYSICAL_ACTIONS:
        logger.info("Motion tool=%s requested=%r clamped=%r", name, args, params)
        state.scene_fresh = False
    try:
        if name == "speak":
            speak(params.get("text"))
            return {"status": "completed"}
        if name == "get_obstacles":
            return controller.get_tof_distances()
        if name == "get_state":
            return {"chassis": controller.get_chassis_state(), "goal": state.current_goal}
        if name in {"forward", "backward", "strafe_left", "strafe_right"}:
            result = getattr(controller, name)(params.get("distance_m"))
        elif name == "turn" and params.get("degrees") == 0:
            result = {"status": "completed", "detail": "zero turn; no movement"}
        elif name == "move_arm" and not any(params.values()):
            result = {"status": "completed", "detail": "zero arm delta; no movement"}
        else:
            result = getattr(controller, name)(**params)
        return {**result, "applied_args": params}
    except Exception as exc:
        logger.exception("Tool=%s failed", name)
        return {"status": "error", "detail": str(exc)}


def _execute_direct(command: dict, state: RobotState, controller: RoboMasterController) -> None:
    started = time.monotonic()
    logger.info("DIRECT parsed command=%r total requested=%r", command.get("verb"), command.get("args"))
    try:
        try:
            calls = decompose_direct_command(command)
        except ValueError as exc:
            logger.error("DIRECT rejected command=%r: %s", command, exc)
            state.last_action_result = {"name": command.get("verb"), "arguments": command.get("args"),
                                        "result": {"status": "rejected", "detail": str(exc)}}
            return
        logger.info("DIRECT local chunks=%r", calls)
        state.last_action_result = {"name": command["verb"], "arguments": command["args"],
                                    "result": {"status": "completed", "completed_chunks": 0, "total_chunks": len(calls)}}
        for index, call in enumerate(calls, 1):
            logger.info("DIRECT chunk=%d/%d tool=%s args=%r", index, len(calls), call["verb"], call["args"])
            result = _execute_verb(call["verb"], call["args"], state, controller, direct=True)
            # Preserve the whole explicit maneuver for the next autonomous step,
            # rather than reporting only its final 90-degree/0.75-m chunk.
            state.last_action_result = {"name": command["verb"], "arguments": command["args"], "result": {
                "status": result.get("status"), "total_chunks": len(calls),
                "completed_chunks": index if result.get("status") == "completed" else index - 1,
                "last_chunk": {"arguments": call["args"], "result": result},
            }}
            if result.get("status") != "completed":
                logger.error("DIRECT maneuver aborted at chunk=%d/%d result=%r", index, len(calls), result)
                _execute_verb("stop", {}, state, controller, direct=True)
                break
    except BaseException:
        _execute_verb("stop", {}, state, controller, direct=True)
        raise
    finally:
        logger.info("DIRECT execution finished duration_s=%.3f", time.monotonic() - started)


async def run_episode(state: RobotState, controller: RoboMasterController) -> RobotState:
    logger.info("episode: starting goal=%r", state.current_goal)
    if not state.last_user_command and state.finished_goal is not None and state.finished_goal == state.current_goal:
        return state
    user_command = state.last_user_command
    command = parse_direct_command(user_command or state.current_goal)
    if command is not None:
        logger.info("execution mode=DIRECT")
        # A direct goal is one-shot, including failures; never replay a partial
        # maneuver on the next episode. A direct stop also ends an active mission.
        if not user_command or command["verb"] == "stop":
            state.finished_goal = state.current_goal
        state.last_user_command = None
        _execute_direct(command, state, controller)
        return state

    logger.info("execution mode=CLOSED_LOOP")
    if state.search_goal != state.current_goal:
        _reset_search(state)
    rotational_search = bool(re.match(
        r"^(?:please\s+)?(?:find|locate|search|look\s+for)\b\s+\S",
        (state.current_goal or "").strip(), re.IGNORECASE,
    ))
    state.scene_fresh = False
    if state.retry_at > time.monotonic():
        return state
    try:
        frame_jpeg = get_latest_frame(controller)
        camera_state = controller.get_camera_state()
        frame_at = camera_state.get("last_frame_monotonic_s")
        logger.info("CLOSED_LOOP frame_age_s=%s", camera_state.get("frame_age_s"))
        if (frame_jpeg is None or not isinstance(frame_at, (int, float))
                or not math.isfinite(frame_at) or frame_at <= state.last_frame_at):
            state.retry_at = time.monotonic() + 0.1
            logger.info("CLOSED_LOOP waiting for a new valid frame; no action")
            return state
        state.last_frame_at = frame_at  # Never decide twice from the same buffered frame.
        pose = controller.get_chassis_state()
        context = {**_mission_context(state), "robot_pose": pose, "scene_fresh": True,
                   "rotational_search": rotational_search}
        if state.current_goal is not None and state.memory_goal != state.current_goal:
            brain.enqueue_memory("mission_context", json.dumps(context, default=str))
            state.memory_goal = state.current_goal
        started = time.monotonic()
        try:
            raw = await decide_action(frame_jpeg, context)
        finally:
            logger.info("CLOSED_LOOP model=%s inference_latency_s=%.3f", ACTION_MODEL, time.monotonic() - started)
        try:
            decision = validate_decision(raw)
            scan_turn = False
            if rotational_search:
                decision, scan_turn = _search_decision(state, decision)
        except ValueError as exc:
            logger.error("CLOSED_LOOP malformed response=%r: %s", raw, exc)
            _retry_cycle(state, exc)
            return state
    except InferenceUnavailable:
        raise
    except Exception as exc:
        logger.warning("CLOSED_LOOP model/frame failure: %s", exc)
        response = getattr(exc, "response", None)
        _retry_cycle(state, exc, response.headers.get("Retry-After") if response is not None else None)
        return state

    state.retry_at, state.consecutive_failures = 0.0, 0
    state.scene_description = decision["observation"]
    state.recent_observations.append(decision["observation"])
    del state.recent_observations[:-8]
    state.last_user_command = None
    name, args = decision["tool"], decision["args"]
    logger.info("CLOSED_LOOP observation=%s", decision["observation"])
    logger.info("CLOSED_LOOP target_visible=%s", decision["target_visible"])
    logger.info("CLOSED_LOOP selected tool=%s args=%r goal_complete=%s", name, args, decision["goal_complete"])
    finding = decision["finding"]
    if finding is not None and finding not in state.findings:
        state.findings.append(finding)
        del state.findings[:-24]
        brain.enqueue_memory(finding["type"], json.dumps({"goal": state.current_goal, "finding": finding,
                                                        "robot_pose": pose}, default=str))
    started = time.monotonic()
    if decision["goal_complete"]:
        state.finished_goal = state.current_goal
    elif name is not None:
        state.scene_fresh = True
        result = _execute_verb(name, args, state, controller)
        state.scene_fresh = False
        state.last_action_result = {"name": name, "arguments": args, "result": result}
        state.last_actions.append(state.last_action_result)
        del state.last_actions[:-8]
        if name in PHYSICAL_ACTIONS:
            # The next frame must arrive after the attempted motion has finished.
            state.last_frame_at = max(state.last_frame_at, time.monotonic())
        if scan_turn and result.get("status") == "completed":
            state.search_rotation_deg += abs(result["applied_args"]["degrees"])
            logger.info("Search direction=%s cumulative_deg=%.1f/360",
                        "left" if state.search_direction > 0 else "right", state.search_rotation_deg)
        if result.get("status") in {"error", "rejected"}:
            _retry_cycle(state, result.get("detail", "tool failed"))
    logger.info("CLOSED_LOOP executor_duration_s=%.3f", time.monotonic() - started)
    state.successful_cycles += 1
    if ((state.finished_goal is not None and state.finished_goal == state.current_goal)
            or state.successful_cycles % MEMORY_SUMMARY_INTERVAL == 0):
        brain.enqueue_memory("mission_summary", json.dumps({**_mission_context(state),
                                                            "goal_complete": decision["goal_complete"]}, default=str))
    return state
