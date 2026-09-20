"""Deliberative episode: RoboMaster perception, planning, and bounded tool execution."""

import logging
import json

from brain import command_parser
from brain.backboard_client import brain
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


def _execute_verb(name: str, args, state: RobotState, controller: RoboMasterController) -> dict:
    """Execute a planner tool without exposing the RoboMaster SDK to the planner."""
    logger.info("Executing tool=%s args=%r", name, args)
    try:
        params = validate_tool_args(name, args)
        if name in PHYSICAL_ACTIONS and not state.scene_fresh:
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


async def run_episode(state: RobotState, controller: RoboMasterController) -> RobotState:
    logger.info("episode: starting goal=%r", state.current_goal)
    state = _perceive(state, controller)

    if state.last_user_command:
        parsed = command_parser.parse(state.last_user_command)
        if parsed is not None:
            name = parsed.get("verb") if isinstance(parsed, dict) else None
            args = parsed.get("args") if isinstance(parsed, dict) else parsed
            result = _execute_verb(name, args, state, controller)
            logger.info("parser fast-path: %s -> %s -> %s", state.last_user_command, parsed, result)
            state.last_action_result = {"name": name, "arguments": args, "result": result}
            state.last_user_command = None
            return state

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
