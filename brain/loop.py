"""Deliberative episode: RoboMaster perception, planning, and bounded tool execution."""

import logging
import math
import json
import time

from brain.backboard_client import brain
from brain.config import STARTUP_SCAN_ENABLED, SCAN_STEP_DEG, CAMERA_SCAN_X_MM, CAMERA_SCAN_HEIGHTS_MM
from brain.direct_commands import decompose_direct_command, parse_direct_command
from brain.state import RobotState
from brain.world_state import WorldState
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
# Camera-mount tuning: normalized image x; gain is a correction heuristic, not FOV telemetry.
TARGET_CENTER_BAND = (0.40, 0.60)
TARGET_ALIGNMENT_HOLD_BAND = (0.35, 0.65)
TARGET_ALIGNMENT_GAIN_DEG = 60.0


def _reset_alignment(state: RobotState) -> None:
    state.active_target = None
    state.target_aligned = False
    state.last_target_position = None
    state.last_alignment_action = None


def _target_alignment_action(state: RobotState, decision: dict) -> tuple:
    """Filter only visual centering turns; never synthesize an unplanned approach."""
    name, args = decision["tool"], decision["args"]
    target = decision["target_alignment"]
    if target is None or not state.current_goal:
        _reset_alignment(state)
        return name, args
    if target["target_id"] != state.active_target:
        _reset_alignment(state)
    state.active_target = target["target_id"]
    x = state.last_target_position = target["center_x"]
    within_deadband = TARGET_CENTER_BAND[0] <= x <= TARGET_CENTER_BAND[1]
    held = state.target_aligned and TARGET_ALIGNMENT_HOLD_BAND[0] <= x <= TARGET_ALIGNMENT_HOLD_BAND[1]
    state.target_aligned = within_deadband or held
    category = ("roughly_centered" if within_deadband else
                "far_left" if x < 0.20 else "left" if x < 0.5 else
                "far_right" if x > 0.80 else "right")
    correcting = target["turn_for_alignment"]
    hysteresis_suppressed = correcting and held and not within_deadband
    angle = None
    if correcting:
        requested = validate_tool_args(name, args)["degrees"]
        # Keep a smaller planner-selected correction for constrained views; cap
        # oversized turns proportionally and use the observed side for direction.
        angle = (0.0 if state.target_aligned else
                 math.copysign(min(abs(requested), TARGET_ALIGNMENT_GAIN_DEG * abs(0.5 - x)), 0.5 - x))
        state.last_alignment_action = {
            "requested_deg": requested, "correction_deg": angle,
            "suppressed": state.target_aligned,
            "reason": "aligned; preserve heading and take the next goal step" if state.target_aligned else "target off-center",
        }
        name, args = (None, {}) if angle == 0 else ("turn", {"degrees": angle})
    logger.info("Target alignment target=%r position=%s center_x=%.3f within_deadband=%s aligned=%s "
                "hysteresis_suppressed=%s correction_deg=%s",
                state.active_target, category, x, within_deadband, state.target_aligned, hysteresis_suppressed, angle)
    return name, args


def _reset_search(state: RobotState) -> None:
    _reset_alignment(state)
    state.target_tracking = "idle"
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
        state.world_state.robot["heading_deg"] = None
        logger.warning("Turn failed; relative heading is now unknown")
    elif result.get("status") == "completed":
        degrees = result["applied_args"]["degrees"]
        if state.relative_heading_deg is not None:
            state.relative_heading_deg = (state.relative_heading_deg + degrees) % 360
        heading = state.world_state.robot["heading_deg"]
        if heading is not None:
            state.world_state.robot["heading_deg"] = (heading + degrees) % 360
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
    state.telemetry.update(phase="retrying", reason=str(error))
    logger.warning("CLOSED_LOOP retry=%d delay_s=%.2f; no action: %s", state.consecutive_failures, delay, error)


def _mission_context(state: RobotState) -> dict:
    return {"current_goal": state.current_goal, "recent_transcript": state.last_user_command,
            "recent_observations": state.recent_observations[-8:], "findings": state.findings[-24:],
            "last_actions": state.last_actions[-8:], "prior_action_result": state.last_action_result,
            "last_camera_adjustment": state.last_camera_adjustment,
            "target_tracking": state.target_tracking,
            "alignment_state": {"active_target": state.active_target, "target_aligned": state.target_aligned,
                                "last_target_position": state.last_target_position,
                                "last_alignment_action": state.last_alignment_action,
                                "center_band": TARGET_CENTER_BAND, "hold_band": TARGET_ALIGNMENT_HOLD_BAND},
            "mission_context": state.mission_context[-8:],
            "search_active": state.search_active, "search_direction": state.search_direction,
            "search_rotation_deg": state.search_rotation_deg,
            "relative_heading_deg": state.relative_heading_deg,
            "world_state": state.world_state.context(), "world_summary": state.world_state.summary(),
            "startup_scan": {"active": state.startup_scan_status == "scanning", "step_deg": SCAN_STEP_DEG,
                             "status": state.startup_scan_status, "rotation_deg": state.startup_scan_rotation_deg},
            "inspected_viewpoints": list(state.inspected_viewpoints)}


def _execute_verb(name: str, args, state: RobotState, controller: RoboMasterController, *, direct: bool = False) -> dict:
    action_id = state.telemetry.start_action(name, args, direct)
    started = time.perf_counter()
    result = {"status": "error", "detail": "execution interrupted"}
    try:
        result = _apply_verb(name, args, state, controller, action_id=action_id, direct=direct)
        return result
    finally:
        state.telemetry.finish_action(action_id, result, (time.perf_counter() - started) * 1000)


def _apply_verb(name: str, args, state: RobotState, controller: RoboMasterController, *, action_id: int, direct: bool = False) -> dict:
    """Execute a planner tool without exposing the RoboMaster SDK to the planner."""
    logger.info("Executing tool=%s args=%r", name, args)
    try:
        params = validate_tool_args(name, args)
        # Only local user commands and fixed startup camera postures may opt
        # out of perception. Planner callbacks/schema cannot supply this flag.
        if name in PHYSICAL_ACTIONS and not direct and not state.scene_fresh:
            raise ValueError("physical action requires a fresh camera scene")
    except ValueError as exc:
        logger.error("Rejected tool=%s args=%r: %s", name, args, exc)
        return {"status": "rejected", "detail": str(exc)}

    state.telemetry.apply_action(action_id, params)
    # An attempted motion can change the view even if the hardware reports an error.
    if name in PHYSICAL_ACTIONS:
        logger.info("Motion tool=%s requested=%r clamped=%r", name, args, params)
        state.scene_fresh = False
        if direct or name in {"turn", "strafe_left", "strafe_right", "move_arm", "recenter_arm"}:
            # These motions invalidate the previous image's alignment latch,
            # including partially failed moves. Forward approach retains it.
            state.target_aligned = False
    if name in {"forward", "backward", "strafe_left", "strafe_right"}:
        state.world_state.bearings_stale = True
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
        result = {**result, "applied_args": params}
    except Exception as exc:
        logger.exception("Tool=%s failed", name)
        result = {"status": "error", "detail": str(exc)}
    if name in {"move_arm", "recenter_arm"}:
        # Retain attempted camera changes, including failures and manual commands,
        # after they leave recent action history. Never infer an absolute camera pose.
        state.last_camera_adjustment = {"name": name, "arguments": params, "result": result,
                                        "observation_before": None if direct else state.scene_description}
        state.world_state.robot["camera_height"] = (
            "HOME" if name == "recenter_arm" else "ADJUSTED"
        ) if result.get("status") == "completed" else "unknown"
    return result


def _start_startup_scan(state: RobotState, controller: RoboMasterController, *, preserve_world: bool = False) -> None:
    if (type(SCAN_STEP_DEG) not in (int, float) or not math.isfinite(SCAN_STEP_DEG)
            or not 0 < SCAN_STEP_DEG <= 90):
        raise ValueError("SCAN_STEP_DEG must be within (0, 90] to fit bounded turn commands")
    if (set(CAMERA_SCAN_HEIGHTS_MM) != {"LOW", "HIGH"}
            or any(type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 80
                   for value in CAMERA_SCAN_HEIGHTS_MM.values())
            or CAMERA_SCAN_HEIGHTS_MM["LOW"] >= CAMERA_SCAN_HEIGHTS_MM["HIGH"]
            or type(CAMERA_SCAN_X_MM) not in (int, float) or not math.isfinite(CAMERA_SCAN_X_MM)
            or not -80 <= CAMERA_SCAN_X_MM <= 80):
        raise ValueError("Scan camera offsets require -80 <= x <= 80 and 0 < LOW < HIGH <= 80 mm from home")
    logger.info("Startup scan started: step_deg=%s", SCAN_STEP_DEG)
    state.startup_scan_status = "scanning"
    if not preserve_world:
        state.world_state = WorldState()
        state.relative_heading_deg = 0.0
    state.startup_scan_rotation_deg = 0.0
    result = _execute_verb("recenter_arm", {}, state, controller, direct=True)
    state.last_action_result = {"name": "recenter_arm", "arguments": {}, "result": result}
    state.last_frame_at = max(state.last_frame_at, time.monotonic())
    if result.get("status") != "completed":
        _abort_startup_scan(state, controller, "camera arm homing failed")
    logger.info("Startup scan arm homed; home is not a forward-looking camera posture")
    _set_startup_camera(state, controller, "LOW")


def _set_startup_camera(state: RobotState, controller: RoboMasterController, height: str) -> None:
    previous = state.world_state.robot["camera_height"]
    args = {"x_mm": CAMERA_SCAN_X_MM if previous == "HOME" else 0,
            "y_mm": CAMERA_SCAN_HEIGHTS_MM[height] - CAMERA_SCAN_HEIGHTS_MM.get(previous, 0)}
    result = _execute_verb("move_arm", args, state, controller, direct=True)
    state.last_action_result = {"name": "move_arm", "arguments": args, "result": result}
    state.last_frame_at = max(state.last_frame_at, time.monotonic())
    if result.get("status") != "completed":
        _abort_startup_scan(state, controller, f"camera {height} positioning failed")
    state.world_state.robot["camera_height"] = height
    logger.info("Startup scan camera moved to %s: x_mm=%s y_mm=%s from home; viewing angle uncalibrated",
                height, CAMERA_SCAN_X_MM, CAMERA_SCAN_HEIGHTS_MM[height])


def _abort_startup_scan(state: RobotState, controller: RoboMasterController, reason: str) -> None:
    state.startup_scan_status = "failed"
    _execute_verb("stop", {}, state, controller, direct=True)
    raise InferenceUnavailable(f"Startup scan aborted: {reason}")


def _advance_startup_scan(state: RobotState, controller: RoboMasterController) -> None:
    # Observe both heights before each turn; twelve fresh views, six +60° turns.
    if state.world_state.robot["camera_height"] == "LOW":
        _set_startup_camera(state, controller, "HIGH")
        return
    if all(obs["view_quality"] in {"poor", "unknown"} for obs in state.world_state.observations[-2:]):
        _abort_startup_scan(state, controller,
                            "both LOW and HIGH views are unusable; edit CAMERA_SCAN_X_MM, CAMERA_LOW_HEIGHT_MM, "
                            "CAMERA_HIGH_HEIGHT_MM in brain/config.py and restart")
    degrees = min(SCAN_STEP_DEG, 360 - state.startup_scan_rotation_deg)
    state.scene_fresh = True
    result = _execute_verb("turn", {"degrees": degrees}, state, controller)
    state.scene_fresh = False
    state.last_action_result = {"name": "turn", "arguments": {"degrees": degrees}, "result": result}
    state.last_actions.append(state.last_action_result)
    del state.last_actions[:-8]
    state.last_frame_at = max(state.last_frame_at, time.monotonic())
    _record_turn(state, result, searching=state.target_tracking == "reacquiring")
    if result.get("status") != "completed":
        _abort_startup_scan(state, controller, "turn failed; coverage is incomplete")
    state.startup_scan_rotation_deg += result["applied_args"]["degrees"]
    if state.startup_scan_rotation_deg >= 360:
        state.startup_scan_status = "completed"
        logger.info("Startup scan completed: observations=%d rotation_deg=%.1f",
                    len(state.world_state.observations), state.startup_scan_rotation_deg)
        logger.info("Startup scan final semantic summary: %s", state.world_state.summary())
    else:
        _set_startup_camera(state, controller, "LOW")


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
    state.telemetry.update(goal=state.current_goal, model=ACTION_MODEL)
    if state.last_user_command:
        state.telemetry.update(last_command=state.last_user_command)
    try:
        await _run_episode(state, controller)
        if state.finished_goal is not None and state.finished_goal == state.current_goal:
            result = (state.last_action_result or {}).get("result", {})
            failed = (state.telemetry.snapshot()["mode"] == "DIRECT"
                      and result.get("status") in {"error", "rejected"})
            state.telemetry.update(phase="failed" if failed else "complete",
                                   reason="Command failed" if failed else "Goal complete")
        elif state.telemetry.snapshot()["phase"] in {"executing", "thinking"}:
            state.telemetry.update(phase="waiting_camera", reason="Waiting for the next observation")
        return state
    except BaseException as exc:
        if state.startup_scan_status == "scanning":
            # Cancellation or exhausted perception may interrupt a physical turn.
            # Never resume the fixed arc with an assumed heading after that.
            state.startup_scan_status = "failed"
            state.world_state.robot["heading_deg"] = None
            state.relative_heading_deg = None
            _execute_verb("stop", {}, state, controller, direct=True)
            logger.error("Startup scan aborted: %s", exc or "interrupted")
        state.telemetry.update(phase="failed", reason=str(exc) or "Mission interrupted")
        raise
    finally:
        state.telemetry.update(scene=state.scene_description, findings=list(state.findings),
                               search_active=state.search_active, search_rotation_deg=state.search_rotation_deg,
                               retry_in_s=max(0.0, state.retry_at - time.monotonic()),
                               failures=state.consecutive_failures, cycles=state.successful_cycles)


async def _run_episode(state: RobotState, controller: RoboMasterController) -> RobotState:
    logger.info("episode: starting goal=%r", state.current_goal)
    if not state.last_user_command and state.finished_goal is not None and state.finished_goal == state.current_goal:
        return state
    if state.search_goal != state.current_goal:
        _reset_search(state)
    user_command = state.last_user_command
    command = parse_direct_command(user_command or state.current_goal)
    if command is not None:
        state.telemetry.update(mode="DIRECT")
        logger.info("execution mode=DIRECT")
        # A direct goal is one-shot, including failures; never replay a partial
        # maneuver on the next episode. A direct stop also ends an active mission.
        if not user_command or command["verb"] == "stop":
            state.finished_goal = state.current_goal
            state.search_active = False
            state.target_tracking = "idle"
        state.last_user_command = None
        if state.startup_scan_status == "scanning" and command["verb"] in PHYSICAL_ACTIONS:
            # Manual motion invalidates this fixed scan; never silently resume its arc.
            state.startup_scan_status = "failed"
        _execute_direct(command, state, controller)
        return state

    logger.info("execution mode=CLOSED_LOOP")
    state.telemetry.update(mode="CLOSED_LOOP")
    state.scene_fresh = False
    if state.retry_at > time.monotonic():
        return state
    if (not state.current_goal and not state.last_user_command
            and (not STARTUP_SCAN_ENABLED or state.startup_scan_status == "completed")):
        return state
    if state.startup_scan_status == "failed":
        raise InferenceUnavailable("Startup scan interrupted; start a new mission state to scan again")
    if STARTUP_SCAN_ENABLED and state.startup_scan_status == "pending":
        _start_startup_scan(state, controller)
        return state
    scanning = state.startup_scan_status == "scanning"
    try:
        # Read the timestamp BEFORE copying the image, so a concurrent decoder
        # update cannot make an older buffered image appear to be post-motion.
        camera_state = controller.get_camera_state()
        frame_jpeg = get_latest_frame(controller)
        frame_at = camera_state.get("last_frame_monotonic_s")
        logger.info("CLOSED_LOOP frame_age_s=%s", camera_state.get("frame_age_s"))
        if (frame_jpeg is None or not isinstance(frame_at, (int, float))
                or not math.isfinite(frame_at) or frame_at <= state.last_frame_at):
            state.retry_at = time.monotonic() + 0.1
            state.telemetry.update(phase="waiting_camera", reason="Waiting for a fresh camera frame")
            logger.info("CLOSED_LOOP waiting for a new valid frame; no action")
            return state
        state.last_frame_at = frame_at  # Never decide twice from the same buffered frame.
        observed_at = time.time()
        pose = controller.get_chassis_state()
        context = {**_mission_context(state), "robot_pose": pose, "scene_fresh": True}
        if not scanning and state.current_goal is not None and state.memory_goal != state.current_goal:
            brain.enqueue_memory("mission_context", json.dumps(context, default=str))
            state.memory_goal = state.current_goal
        started = time.monotonic()
        state.telemetry.update(phase="thinking", reason="Interpreting the camera frame")
        try:
            raw = await decide_action(frame_jpeg, context)
        finally:
            elapsed = time.monotonic() - started
            state.telemetry.update(inference_ms=elapsed * 1000)
            logger.info("CLOSED_LOOP model=%s inference_latency_s=%.3f", ACTION_MODEL, elapsed)
        try:
            decision = validate_decision(raw)
            if scanning and "world_observation" not in decision:
                raise ValueError("startup scan requires a semantic world_observation")
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
    if "world_observation" in decision:
        state.world_state.observe(decision["observation"], decision["world_observation"], observed_at)
    if state.target_tracking == "reacquiring":
        if decision["target_visible"]:
            state.target_tracking = "approaching"
            logger.info("Target reacquired; interrupting scan and resuming goal=%r", state.current_goal)
        else:
            # Losing sight never completes an approach, even after a full scan.
            decision["goal_complete"] = False
            decision["search_active"] = True
    if scanning:
        logger.info("Startup scan observation heading_deg=%s camera_height=%s view_quality=%s summary=%s",
                    state.world_state.robot["heading_deg"], state.world_state.robot["camera_height"],
                    decision["world_observation"]["view_quality"],
                    decision["observation"])
        if state.current_goal and decision["target_visible"]:
            state.startup_scan_status = "target_found"
            logger.info("Startup scan ended early: target visible goal=%r heading_deg=%s camera_height=%s rotation_deg=%.1f",
                        state.current_goal, state.world_state.robot["heading_deg"],
                        state.world_state.robot["camera_height"], state.startup_scan_rotation_deg)
            logger.info("Startup scan final semantic summary: %s", state.world_state.summary())
            # Fall through to normal execution using this already-validated image
            # decision. No extra inference, scan turn, or camera change first.
        else:
            state.scene_description = decision["observation"]
            state.telemetry.update(scene=state.scene_description, scene_at=observed_at)
            state.recent_observations.append(state.scene_description)
            del state.recent_observations[:-8]
            _advance_startup_scan(state, controller)
            return state
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
    state.telemetry.update(scene=state.scene_description, scene_at=time.time())
    state.recent_observations.append(decision["observation"])
    del state.recent_observations[:-8]
    state.last_user_command = None
    if state.target_tracking == "approaching" and not decision["target_visible"]:
        logger.info("Target lost during approach: target=%r goal=%r observation=%s; stopping and restarting scan",
                    state.active_target, state.current_goal, decision["observation"])
        state.target_tracking = "reacquiring"
        _reset_alignment(state)
        state.search_active = True
        state.search_direction, state.search_rotation_deg = 1, 0.0
        result = _execute_verb("stop", {}, state, controller, direct=True)
        state.last_action_result = {"name": "stop", "arguments": {}, "result": result}
        if result.get("status") != "completed":
            raise InferenceUnavailable("Cannot restart target scan: stop failed")
        _start_startup_scan(state, controller, preserve_world=True)
        return state
    name, args = _target_alignment_action(state, decision)
    if (state.target_tracking == "reacquiring" and name in PHYSICAL_ACTIONS
            and name not in {"turn", "move_arm", "recenter_arm"}):
        logger.info("Target still absent; suppressing tool=%s until reacquired", name)
        name, args = "stop", {}
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
        state.target_tracking = "idle"
    elif name is not None:
        if (state.current_goal and decision["target_visible"]
                and name in {"forward", "backward", "strafe_left", "strafe_right"}):
            # Keep tracking through intervening alignment/camera actions and even
            # failed translations, which may have moved the chassis partially.
            state.target_tracking = "approaching"
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
