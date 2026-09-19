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
    {
        "type": "function",
        "function": {
            "name": "get_temperature",
            "description": "Read the ambient temperature sensor. Returns celsius and status (ok/warm/overheat). Useful for detecting fire or hazardous heat.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_audio",
            "description": "Read the microphone for ambient sound level and detected audio events. Events include distress (screams, calls for help), sound (hazard noise like rubble or creaking), and voice (operator commands). Returns dB level and event details if something was detected.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_gyro",
            "description": "Read the IMU/gyroscope for tilt, impact, and orientation. Returns pitch, roll, vertical acceleration, tipped (bool), and bump (bool). Use to detect if the robot has been picked up, flipped, or bumped into something.",
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

You have environmental sensors: get_temperature (detect fire or hazardous heat), \
get_audio (listen for distress calls, hazard noise, or operator voices), and get_gyro \
(detect tipping, impacts, or being picked up). Poll these when the situation calls for it \
-- a survivor may be calling for help that only the microphone can hear, or a hot spot \
may only be detectable by the temperature sensor.

Use speak() the way a real rescue responder would: calm, clear, reassuring, brief. \
Narrate what matters as you find it -- a hazard, an obstacle, a person -- don't stay \
silent through something worth reporting. If a spoken command is present, treat it as a \
person you can hear talking to you: acknowledge it and respond directly, then act on it."""
