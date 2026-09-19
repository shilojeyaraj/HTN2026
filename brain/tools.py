"""The brain's fixed verb set: bounded, self-completing motion primitives (CLAUDE.md
section 6). Keep this schema small and stable so the fixed prompt prefix stays cacheable.
"""

VERBS = [
    {
        "type": "function",
        "function": {
            "name": "forward",
            "description": "Drive forward distance_m meters, then stop. Returns 'completed' or 'stopped_by_obstacle'.",
            "parameters": {"type": "object", "properties": {"distance_m": {"type": "number"}}, "required": ["distance_m"]},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "backward",
            "description": "Drive backward distance_m meters, then stop.",
            "parameters": {"type": "object", "properties": {"distance_m": {"type": "number"}}, "required": ["distance_m"]},
        },
    },
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
            "description": "Read the latest on-camera obstacle detections without moving.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_state",
            "description": "Read the robot's current pose, velocity, and goal without moving.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]

SYSTEM_PROMPT = """You are a rescue rover: a small autonomous robot that explores hazardous \
or hard-to-reach spaces to look for people and report what you find. You receive a scene \
description, the current goal, and any spoken command from someone nearby.

Move by calling forward/backward/turn in small bounded steps; check progress with \
get_obstacles/get_state. Each movement verb reports back whether it completed or stopped \
early due to an obstacle -- use that to decide your next call. Never invent motor \
commands outside the provided tools.

Use speak() the way a real rescue responder would: calm, clear, reassuring, brief. \
Narrate what matters as you find it -- a hazard, an obstacle, a person -- don't stay \
silent through something worth reporting. If a spoken command is present, treat it as a \
person you can hear talking to you: acknowledge it and respond directly, then act on it."""
