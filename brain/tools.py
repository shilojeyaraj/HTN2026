"""The planner's bounded RoboMaster action and observation vocabulary."""

import json
import math
from pathlib import Path


RESCUE_PROTOCOLS = (Path(__file__).resolve().parent.parent / "knowledge" / "rescue_protocols.md").read_text()


def _distance_tool(name: str, description: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {"distance_m": {"type": "number", "minimum": 0.05, "maximum": 0.5}},
                "required": ["distance_m"],
            },
        },
    }


VERBS = [
    _distance_tool("forward", "Drive forward distance_m metres, then stop."),
    _distance_tool("backward", "Drive backward distance_m metres, then stop."),
    _distance_tool("strafe_left", "Drive left distance_m metres, then stop."),
    _distance_tool("strafe_right", "Drive right distance_m metres, then stop."),
    {
        "type": "function",
        "function": {
            "name": "turn",
            "description": "Turn in place by degrees (positive = left, negative = right), then stop.",
            "parameters": {"type": "object", "properties": {"degrees": {"type": "number", "minimum": -45, "maximum": 45}}, "required": ["degrees"]},
        },
    },
    {
        "type": "function",
        "function": {"name": "stop", "description": "Halt immediately.", "parameters": {"type": "object", "properties": {}}},
    },
    {
        "type": "function",
        "function": {
            "name": "move_arm",
            "description": "Move the camera arm relative to its current position in millimetres: x_mm forward/back, y_mm up/down. Keep each value within 80 mm.",
            "parameters": {"type": "object", "properties": {
                "x_mm": {"type": "number", "minimum": -80, "maximum": 80},
                "y_mm": {"type": "number", "minimum": -80, "maximum": 80},
            }, "required": ["x_mm", "y_mm"]},
        },
    },
    {
        "type": "function",
        "function": {"name": "recenter_arm", "description": "Return the camera arm to centre.", "parameters": {"type": "object", "properties": {}}},
    },
    {
        "type": "function",
        "function": {"name": "open_gripper", "description": "Open the claw at safe low power, then pause it.", "parameters": {"type": "object", "properties": {}}},
    },
    {
        "type": "function",
        "function": {"name": "close_gripper", "description": "Close the claw at safe low power, then pause it.", "parameters": {"type": "object", "properties": {}}},
    },
    {
        "type": "function",
        "function": {
            "name": "speak",
            "description": "Say something out loud via TTS.",
            "parameters": {"type": "object", "properties": {"text": {"type": "string", "minLength": 1, "maxLength": 240}}, "required": ["text"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_obstacles",
            "description": "Read raw RoboMaster ToF sensor values in millimetres. Values have no inferred bearings.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_state",
            "description": "Read received RoboMaster chassis telemetry and the current goal without moving.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

PHYSICAL_ACTIONS = frozenset({
    "forward", "backward", "strafe_left", "strafe_right", "turn",
    "move_arm", "recenter_arm", "open_gripper", "close_gripper",
})
TOOL_PARAMETERS = {tool["function"]["name"]: tool["function"]["parameters"] for tool in VERBS}
for parameters in TOOL_PARAMETERS.values():
    parameters["additionalProperties"] = False


def validate_tool_args(name: str, args) -> dict:
    """Decode untrusted arguments and return bounded values, or raise ValueError."""
    if not isinstance(name, str) or name not in TOOL_PARAMETERS:
        raise ValueError(f"unknown tool {name!r}")
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except (ValueError, RecursionError) as exc:
            raise ValueError("arguments must be a valid JSON object") from exc
    if not isinstance(args, dict):
        raise ValueError("arguments must be an object")

    schema = TOOL_PARAMETERS[name]
    missing = [key for key in schema.get("required", []) if key not in args]
    if missing:
        raise ValueError(f"missing required argument(s): {', '.join(missing)}")
    if args.keys() - schema["properties"].keys():
        raise ValueError("unexpected argument(s); use the exact tool schema")

    validated = {}
    for key, rule in schema["properties"].items():
        value = args.get(key)
        if rule["type"] == "number":
            if isinstance(value, bool) or not isinstance(value, (str, int, float)):
                raise ValueError(f"{key} must be a finite number")
            try:
                value = float(value)
            except (ValueError, OverflowError) as exc:
                raise ValueError(f"{key} must be a finite number") from exc
            if not math.isfinite(value):
                raise ValueError(f"{key} must be a finite number")
            value = max(rule["minimum"], min(value, rule["maximum"]))
        else:
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{key} must be non-empty text")
            value = value.strip()[:rule["maxLength"]]
        validated[key] = value
    return validated

SYSTEM_PROMPT = """You are a rescue rover: a small autonomous robot that explores hazardous \
or hard-to-reach spaces to look for people and report what you find. You receive a scene \
description, the current goal, and any spoken command from someone nearby.

Move by calling forward/backward/strafe_left/strafe_right/turn in small bounded steps. \
Use get_state for real chassis telemetry. get_obstacles returns raw ToF readings only; do \
not invent their direction or treat an absent reading as clear space. Never invent motor \
commands outside the provided tools.

Request at most one physical action per scene: a chassis move, turn, arm move, \
recenter, or gripper action. After that action, wait for fresh perception before \
planning another physical action. Rejected or skipped tools did not execute. \
Use exact argument names: distance_m, degrees, x_mm and y_mm, or text. \
Keep distances within 0.05–0.5 m, turns within -45–45 degrees, and arm deltas \
within -80–80 mm. If scene_fresh is false, use only non-physical tools.

The camera arm moves forward/back and up/down; use turn to look left or right. Use \
move_arm only for a better view, then recenter_arm when finished. Use the gripper only \
when the mission requires handling an object.

Use speak() the way a real rescue responder would: calm, clear, reassuring, brief. \
Narrate what matters as you find it -- a hazard, an obstacle, a person -- don't stay \
silent through something worth reporting. If a spoken command is present, treat it as a \
person you can hear talking to you: acknowledge it and respond directly, then act on it.

Rescue protocols:
""" + RESCUE_PROTOCOLS
