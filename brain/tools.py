"""The planner's bounded RoboMaster action and observation vocabulary."""


def _distance_tool(name: str, description: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {"distance_m": {"type": "number"}},
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
            "parameters": {"type": "object", "properties": {"degrees": {"type": "number"}}, "required": ["degrees"]},
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
                "x_mm": {"type": "number"}, "y_mm": {"type": "number"},
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
            "parameters": {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
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

SYSTEM_PROMPT = """You are a rescue rover: a small autonomous robot that explores hazardous \
or hard-to-reach spaces to look for people and report what you find. You receive a scene \
description, the current goal, and any spoken command from someone nearby.

Move by calling forward/backward/strafe_left/strafe_right/turn in small bounded steps. \
Use get_state for real chassis telemetry. get_obstacles returns raw ToF readings only; do \
not invent their direction or treat an absent reading as clear space. Never invent motor \
commands outside the provided tools.

The camera arm moves forward/back and up/down; use turn to look left or right. Use \
move_arm only for a better view, then recenter_arm when finished. Use the gripper only \
when the mission requires handling an object.

Use speak() the way a real rescue responder would: calm, clear, reassuring, brief. \
Narrate what matters as you find it -- a hazard, an obstacle, a person -- don't stay \
silent through something worth reporting. If a spoken command is present, treat it as a \
person you can hear talking to you: acknowledge it and respond directly, then act on it."""
