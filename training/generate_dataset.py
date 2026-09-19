"""Generate a command-to-verb JSONL dataset for fine-tuning a robot command parser.

Each row: {"prompt": "<natural language command>", "completion": "<JSON verb call>"}

Run: python training/generate_dataset.py
Output: training/dataset.jsonl
"""

import json
import random

random.seed(42)

forward_templates = [
    "forward {d} meters", "move forward {d} meters", "go forward {d}m",
    "drive forward {d} meters", "advance {d} meters", "go ahead {d} meters",
    "move ahead {d}m", "go straight {d} meters", "head forward {d} meters",
    "move {d} meters forward", "drive {d} meters ahead", "proceed forward {d} meters",
    "crawl forward {d} meters", "go {d} meters ahead", "straight ahead {d}m",
    "push forward {d} meters", "inch forward {d} meters", "roll forward {d}m",
]

backward_templates = [
    "backward {d} meters", "move backward {d} meters", "go back {d} meters",
    "reverse {d} meters", "back up {d} meters", "drive backward {d}m",
    "retreat {d} meters", "go backward {d} meters", "move back {d}m",
    "drive back {d} meters", "pull back {d} meters", "back away {d}m",
]

turn_left_templates = [
    "turn left {d} degrees", "rotate left {d}", "turn {d} degrees left",
    "face {d} degrees left", "pivot left {d} degrees", "swing left {d}",
    "bear left {d} degrees", "veer left {d} degrees", "turn left {d}",
    "rotate {d} degrees left", "yaw left {d} degrees",
]

turn_right_templates = [
    "turn right {d} degrees", "rotate right {d}", "turn {d} degrees right",
    "face {d} degrees right", "pivot right {d} degrees", "swing right {d}",
    "bear right {d} degrees", "veer right {d} degrees", "turn right {d}",
    "rotate {d} degrees right", "yaw right {d} degrees",
]

turn_absolute_templates = [
    "turn {d} degrees", "rotate {d} degrees", "face {d} degrees",
    "turn to {d} degrees", "rotate to {d}",
]

stop_templates = [
    "stop", "halt", "freeze", "stop now", "stop right now", "hold",
    "hold position", "stay", "brake", "stop moving", "hold still",
    "stop immediately", "cease movement", "stand by", "wait",
    "stop right there", "don't move", "hold up",
]

speak_texts = [
    "Is anyone there? Can you hear me?",
    "Help is on the way. Stay calm.",
    "I'm a rescue rover. I'm here to help.",
    "Can you make a sound if you can hear me?",
    "I've found someone. Sending location.",
    "The path ahead is clear. Proceeding.",
    "I detect a hazard. Marking the area.",
    "Stay where you are. Help is coming.",
    "I hear you. I'm coming toward you.",
    "The area is safe. You can move now.",
]

speak_templates = [
    "say {text}", "speak {text}", 'say "{text}"', "announce {text}",
    "call out {text}", "broadcast {text}", "tell them {text}",
    "shout {text}", "report {text}", "narrate {text}",
]

get_obstacles_templates = [
    "what do you see", "report obstacles", "what's ahead", "what's in front",
    "show obstacles", "list obstacles", "what's around you", "scan ahead",
    "report surroundings", "what obstacles are there", "describe what's ahead",
    "check for obstacles", "what's in the way", "any obstacles",
    "report what you see", "look ahead", "what can you detect",
    "give me a sitrep", "what's out there",
]

get_state_templates = [
    "where are you", "report status", "what's your state", "current position",
    "where are you now", "report pose", "what's your location", "status report",
    "where are you located", "what's your heading", "report your state",
    "current status", "position report", "where am i", "what's your position",
    "give me your coordinates", "what's your situation",
]


def _row(prompt, verb, args=None):
    return {"prompt": prompt, "completion": json.dumps({"verb": verb, "args": args or {}})}


rows = []

for tmpl in forward_templates:
    for d in [0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 0.3, 10.0]:
        rows.append(_row(tmpl.format(d=d), "forward", {"distance_m": d}))

for tmpl in backward_templates:
    for d in [0.5, 1.0, 1.5, 2.0, 3.0, 0.3]:
        rows.append(_row(tmpl.format(d=d), "backward", {"distance_m": d}))

for tmpl in turn_left_templates:
    for d in [30, 45, 60, 90, 120, 180]:
        rows.append(_row(tmpl.format(d=d), "turn", {"degrees": d}))

for tmpl in turn_right_templates:
    for d in [30, 45, 60, 90, 120, 180]:
        rows.append(_row(tmpl.format(d=d), "turn", {"degrees": -d}))

for tmpl in turn_absolute_templates:
    for d in [30, 45, 90, 180, -30, -45, -90, -180, 15, 270]:
        rows.append(_row(tmpl.format(d=d), "turn", {"degrees": d}))

for tmpl in stop_templates:
    rows.append(_row(tmpl, "stop"))

for tmpl in speak_templates:
    for text in speak_texts:
        rows.append(_row(tmpl.format(text=text), "speak", {"text": text}))

for tmpl in get_obstacles_templates:
    rows.append(_row(tmpl, "get_obstacles"))

for tmpl in get_state_templates:
    rows.append(_row(tmpl, "get_state"))

random.shuffle(rows)

with open("training/dataset.jsonl", "w") as f:
    for row in rows:
        f.write(json.dumps(row) + "\n")

print(f"Generated {len(rows)} examples -> training/dataset.jsonl")
