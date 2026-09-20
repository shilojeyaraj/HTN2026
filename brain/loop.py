"""Deliberative episode: RoboMaster perception, planning, and bounded tool execution."""

import logging
import json
import time

from brain.backboard_client import brain
from brain.direct_commands import decompose_direct_command, parse_direct_command
from brain.state import RobotState
from brain.tools import PHYSICAL_ACTIONS, SYSTEM_PROMPT, VERBS, validate_tool_args
from control.robomaster import RoboMasterController
from perception.camera import get_latest_frame
from perception.vision import describe_scene
from voice.tts import speak

logger = logging.getLogger(__name__)


def _perceive(state: RobotState, controller: RoboMasterController) -> RobotState:
    state.scene_fresh = False
    try:
        logger.info("perception: requesting latest camera frame")
        frame_jpeg = get_latest_frame(controller)
        if frame_jpeg is None:
            logger.warning("RoboMaster camera did not provide a frame")
        else:
            logger.info("perception: received %d-byte JPEG", len(frame_jpeg))
            description = describe_scene(frame_jpeg)
            if description:
                state.scene_description = description
                state.scene_fresh = True
            else:
                logger.warning("vision returned no scene description; keeping prior scene")
    except Exception:
        logger.warning("vision failed, keeping prior scene_description", exc_info=True)
    return state


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
    state = _perceive(state, controller)

    if not state.scene_fresh:
        logger.warning("episode: waiting for valid vision; skipping planner and movement")
        return state

    user_content = json.dumps(
        {
            "scene_description": state.scene_description,
            "scene_fresh": state.scene_fresh,
            "robot_pose": controller.get_chassis_state(),
            "recent_transcript": state.last_user_command,
            "current_goal": state.current_goal,
            "prior_action_result": state.last_action_result,
        },
        default=str,
    )
    state.last_user_command = None

    results = await brain.run_tools(
        content=user_content,
        system_prompt=SYSTEM_PROMPT,
        tools=VERBS,
        execute_tool=lambda name, args: _execute_verb(name, args, state, controller),
        memory="Auto",
    )
    if results:
        state.last_action_result = results[-1]
    logger.info("episode: planner completed %d tool call(s)", len(results))
    return state
