"""Deliberative episode: RoboMaster perception, planning, and bounded tool execution."""

import logging

from brain import command_parser
from brain.backboard_client import brain
from brain.state import RobotState
from brain.tools import SYSTEM_PROMPT, VERBS
from control.robomaster import RoboMasterController, RoboMasterError
from perception.camera import get_latest_frame
from perception.vision import describe_scene
from voice.tts import speak

logger = logging.getLogger(__name__)


def _perceive(state: RobotState, controller: RoboMasterController) -> RobotState:
    try:
        frame_jpeg = get_latest_frame(controller)
        if frame_jpeg is None:
            logger.warning("RoboMaster camera did not provide a frame")
        else:
            state.scene_description = describe_scene(frame_jpeg)
    except Exception:
        logger.warning("vision failed, keeping prior scene_description", exc_info=True)
    return state


def _execute_verb(name: str, args: dict, state: RobotState, controller: RoboMasterController) -> dict:
    """Execute a planner tool without exposing the RoboMaster SDK to the planner."""
    if name == "speak":
        speak(args["text"])
        return {"status": "completed"}
    if name == "get_obstacles":
        return controller.get_tof_distances()
    if name == "get_state":
        return {"chassis": controller.get_chassis_state(), "goal": state.current_goal}

    movement = {
        "forward": lambda: controller.forward(args["distance_m"]),
        "backward": lambda: controller.backward(args["distance_m"]),
        "strafe_left": lambda: controller.strafe_left(args["distance_m"]),
        "strafe_right": lambda: controller.strafe_right(args["distance_m"]),
        "turn": lambda: controller.turn(args["degrees"]),
        "stop": controller.stop,
        "move_arm": lambda: controller.move_arm(args.get("x_mm", 0), args.get("y_mm", 0)),
        "recenter_arm": controller.recenter_arm,
        "open_gripper": controller.open_gripper,
        "close_gripper": controller.close_gripper,
    }.get(name)
    if movement is None:
        return {"status": "error", "detail": f"unknown verb {name}"}
    try:
        return movement()
    except (RoboMasterError, ValueError) as exc:
        logger.warning("RoboMaster verb %s failed: %s", name, exc)
        return {"status": "error", "detail": str(exc)}


def run_episode(state: RobotState, controller: RoboMasterController) -> RobotState:
    state = _perceive(state, controller)

    if state.last_user_command:
        parsed = command_parser.parse(state.last_user_command)
        if parsed is not None:
            result = _execute_verb(parsed["verb"], parsed["args"], state, controller)
            logger.info("parser fast-path: %s -> %s -> %s", state.last_user_command, parsed, result)
            state.last_user_command = None
            return state

    user_content = (
        f"Scene: {state.scene_description}\n"
        f"Current goal: {state.current_goal}\n"
        f"User command: {state.last_user_command}\n"
        f"Chassis telemetry: {controller.get_chassis_state()}"
    )
    state.last_user_command = None

    brain.run_tools(
        content=user_content,
        system_prompt=SYSTEM_PROMPT,
        tools=VERBS,
        execute_tool=lambda name, args: _execute_verb(name, args, state, controller),
        memory="Auto",
    )
    return state
