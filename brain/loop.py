"""Deliberative episode: RoboMaster perception, planning, and bounded tool execution."""

import logging
import math
import json
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
MAX_INSPECTED_VIEWPOINTS = 36


def _reset_search(state: RobotState) -> None:
    state.search_active = False
    state.search_direction = 0
    state.search_rotation_deg = 0.0
    state.search_goal = state.current_goal
    state.relative_heading_deg = 0.0
    state.inspected_viewpoints.clear()


def _record_turn(state: RobotState, result: dict, *, searching: bool) -> None:
    """Update estimates only from completed, validated commands, including DIRECT."""
    if result.get("status") == "error":
        state.relative_heading_deg = None  # A failed SDK action may have moved partially.
        logger.warning("Turn failed; relative heading is now unknown")
    elif result.get("status") == "completed":
        degrees = result["applied_args"]["degrees"]
        if state.relative_heading_deg is not None:
            state.relative_heading_deg = (state.relative_heading_deg + degrees) % 360
        if searching and degrees:
            state.search_direction = 1 if degrees > 0 else -1
            state.search_rotation_deg += abs(degrees)
            logger.info("Search direction=%s cumulative_deg=%.1f relative_heading_deg=%s",
                        "left" if degrees > 0 else "right", state.search_rotation_deg, state.relative_heading_deg)


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
            "search_rotation_deg": state.search_rotation_deg,
            "relative_heading_deg": state.relative_heading_deg,
            "inspected_viewpoints": list(state.inspected_viewpoints)}


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
            if call["verb"] == "turn":
                _record_turn(state, result, searching=False)
            if call["verb"] in PHYSICAL_ACTIONS:
                state.last_frame_at = max(state.last_frame_at, time.monotonic())
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
    if state.search_goal != state.current_goal:
        _reset_search(state)
    user_command = state.last_user_command
    command = parse_direct_command(user_command or state.current_goal)
    if command is not None:
        logger.info("execution mode=DIRECT")
        # A direct goal is one-shot, including failures; never replay a partial
        # maneuver on the next episode. A direct stop also ends an active mission.
        if not user_command or command["verb"] == "stop":
            state.finished_goal = state.current_goal
            state.search_active = False
        state.last_user_command = None
        _execute_direct(command, state, controller)
        return state

    logger.info("execution mode=CLOSED_LOOP")
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
        context = {**_mission_context(state), "robot_pose": pose, "scene_fresh": True}
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
    was_searching = state.search_active
    state.search_active = (decision.get("search_active", was_searching)
                           and not decision["target_visible"] and not decision["goal_complete"])
    if state.search_active and not was_searching:
        logger.info("Search started: goal=%r", state.current_goal)
    if was_searching and decision["target_visible"]:
        logger.info("Search target detected: goal=%r cumulative_deg=%.1f", state.current_goal, state.search_rotation_deg)
    # Record the view before acting. Keep this history longer than recent actions;
    # a revisited heading, poor image, or changed position is not proof of coverage.
    state.inspected_viewpoints.append({"relative_heading_deg": state.relative_heading_deg,
                                       "robot_pose": pose, "observation": decision["observation"],
                                       "target_visible": decision["target_visible"]})
    del state.inspected_viewpoints[:-MAX_INSPECTED_VIEWPOINTS]
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
        if name == "turn":
            _record_turn(state, result, searching=state.search_active)
        if result.get("status") in {"error", "rejected"}:
            _retry_cycle(state, result.get("detail", "tool failed"))
    logger.info("CLOSED_LOOP executor_duration_s=%.3f", time.monotonic() - started)
    state.successful_cycles += 1
    if ((state.finished_goal is not None and state.finished_goal == state.current_goal)
            or state.successful_cycles % MEMORY_SUMMARY_INTERVAL == 0):
        brain.enqueue_memory("mission_summary", json.dumps({**_mission_context(state),
                                                            "goal_complete": decision["goal_complete"]}, default=str))
    return state
