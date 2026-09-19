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

SYSTEM_PROMPT = """You are the planner for a small autonomous rover. You receive a scene \
description, a fine-tuned model's read on the venue, the current goal, and any spoken \
user command. Move by calling forward/backward/turn in small bounded steps; check \
progress with get_obstacles/get_state; narrate with speak(). Each movement verb reports \
back whether it completed or stopped early due to an obstacle -- use that to decide your \
next call. Never invent motor commands outside the provided tools."""
