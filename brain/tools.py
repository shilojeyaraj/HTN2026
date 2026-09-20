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

Use speak() the way a real rescue responder would: calm, clear, reassuring, brief. \
Narrate what matters as you find it -- a hazard, an obstacle, a person -- don't stay \
silent through something worth reporting. If a spoken command is present, treat it as a \
person you can hear talking to you: acknowledge it and respond directly, then act on it."""
