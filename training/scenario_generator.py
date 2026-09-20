"""Rescue scenario generator: creates simulated disaster environments for
training the rescue decision model.

Each scenario includes:
- Environment description (building type, damage level, layout)
- Sensor readings (temperature, audio, gyro, camera depth) with noise
- Victim locations and conditions
- Hazard locations and types
- The "messy" factor: missing readings, conflicting data, noise

Scenarios are generated procedurally with controlled randomness, then
enriched by Gemini for narrative variety.
"""

import json
import math
import random
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ENVIRONMENT_TYPES = [
    "collapsed_apartment",
    "industrial_warehouse",
    "underground_tunnel",
    "school_gymnasium",
    "parking_structure",
    "hospital_wing",
    "transit_station",
    "shopping_mall",
]

HAZARD_TYPES = ["fire", "structural_collapse", "gas_leak", "flood", "electrical", "debris"]

VICTIM_CONDITIONS = ["conscious_uninjured", "conscious_injured", "trapped", "unconscious"]


def generate_scenario(complexity: int = 1, seed: int | None = None) -> dict:
    """Generate a single rescue scenario with messy sensor data.

    Args:
        complexity: 1-5, higher = more hazards, victims, and noise
        seed: random seed for reproducibility
    """
    rng = random.Random(seed)
    env_type = rng.choice(ENVIRONMENT_TYPES)

    num_hazards = rng.randint(1, complexity)
    num_victims = rng.randint(1, complexity + 1)
    room_size = 4.0 + complexity * 2.0

    # Generate obstacles (walls, rubble) with positions
    obstacles = []
    for i in range(rng.randint(3, 3 + complexity * 2)):
        obstacles.append({
            "x": round(rng.uniform(-room_size, room_size), 2),
            "y": round(rng.uniform(-room_size, room_size), 2),
            "radius": round(rng.uniform(0.2, 0.5), 2),
            "type": rng.choice(["wall", "rubble", "debris", "vehicle"]),
        })

    # Generate hazards
    hazards = []
    for i in range(num_hazards):
        h_type = rng.choice(HAZARD_TYPES)
        hazards.append({
            "x": round(rng.uniform(-room_size, room_size), 2),
            "y": round(rng.uniform(-room_size, room_size), 2),
            "type": h_type,
            "severity": rng.choice(["low", "medium", "high"]),
        })

    # Generate victims
    victims = []
    for i in range(num_victims):
        victims.append({
            "x": round(rng.uniform(-room_size, room_size), 2),
            "y": round(rng.uniform(-room_size, room_size), 2),
            "condition": rng.choice(VICTIM_CONDITIONS),
            "conscious": rng.random() > 0.3,
            "speaking": rng.random() > 0.5,
            "distress_call": rng.random() > 0.7,
        })

    # Generate messy sensor readings
    # Temperature: sometimes hot near fire hazards, sometimes noisy
    base_temp = rng.uniform(18.0, 28.0)
    temp_noise = rng.uniform(-2.0, 2.0)
    has_heat = any(h["type"] == "fire" for h in hazards)
    temperature = {
        "celsius": round(base_temp + temp_noise + (40.0 if has_heat else 0.0), 1),
        "status": "ok",
        "noise": round(temp_noise, 1),
    }
    if temperature["celsius"] >= 60:
        temperature["status"] = "overheat"
    elif temperature["celsius"] >= 40:
        temperature["status"] = "warm"

    # Audio: distress calls if victims are speaking
    has_distress = any(v["distress_call"] for v in victims)
    audio = {
        "db": round(rng.uniform(30.0, 90.0 if has_distress else 50.0), 1),
        "event": None,
        "noise": round(rng.uniform(-5.0, 5.0), 1),
    }
    if has_distress:
        audio["event"] = {
            "kind": "distress",
            "label": rng.choice(["help me", "is anyone there", "I'm trapped", "over here"]),
            "bearing_deg": round(rng.uniform(-180, 180), 1),
        }

    # Gyro: sometimes bumped
    gyro = {
        "pitch_deg": round(rng.uniform(-5.0, 5.0), 1),
        "roll_deg": round(rng.uniform(-5.0, 5.0), 1),
        "tipped": rng.random() < 0.05 * complexity,
        "bump": rng.random() < 0.15 * complexity,
    }

    # Camera depth: obstacle detections with noise
    detections = []
    for obs in obstacles[:5]:  # only nearby obstacles
        dist = math.sqrt(obs["x"]**2 + obs["y"]**2)
        if dist < 5.0:
            bearing = math.degrees(math.atan2(obs["y"], obs["x"]))
            dist_noise = rng.uniform(-0.3, 0.3)
            detections.append({
                "label": "obstacle",
                "distance_m": round(max(0.1, dist + dist_noise), 2),
                "bearing_deg": round(bearing + rng.uniform(-10, 10), 1),
                "type": obs["type"],
            })

    # Missing data factor: sometimes drop readings
    missing_sensors = []
    if rng.random() < 0.1 * complexity:
        missing_sensors.append(rng.choice(["temperature", "audio", "gyro", "camera"]))
    if rng.random() < 0.05 * complexity:
        missing_sensors.append(rng.choice(["temperature", "audio", "gyro", "camera"]))

    # Conflicting data: sometimes depth says free but temperature says hot
    conflicting = False
    if has_heat and rng.random() < 0.3:
        conflicting = True

    # Scene description for the brain
    scene_parts = []
    if detections:
        scene_parts.append(f"{len(detections)} obstacles nearby, closest at {min(d['distance_m'] for d in detections):.1f}m")
    else:
        scene_parts.append("open space ahead")
    if temperature["status"] != "ok":
        scene_parts.append(f"temperature {temperature['celsius']}°C ({temperature['status']})")
    if audio["event"]:
        scene_parts.append(f"audio: {audio['event']['label']} at {audio['db']}dB")
    if gyro["bump"]:
        scene_parts.append("recent bump detected")
    if conflicting:
        scene_parts.append("WARNING: conflicting sensor readings")

    return {
        "id": f"SIM-{seed or rng.randint(10000, 99999)}",
        "environment_type": env_type,
        "room_size_m": room_size,
        "obstacles": obstacles,
        "hazards": hazards,
        "victims": victims,
        "sensor_readings": {
            "temperature": temperature,
            "audio": audio,
            "gyro": gyro,
            "detections": detections,
        },
        "missing_sensors": missing_sensors,
        "conflicting_data": conflicting,
        "scene_description": ". ".join(scene_parts) + ".",
        "complexity": complexity,
    }


def generate_batch(count: int = 100, complexity_range: tuple = (1, 3), seed_base: int = 0) -> list[dict]:
    """Generate a batch of scenarios with varying complexity."""
    scenarios = []
    for i in range(count):
        complexity = random.randint(complexity_range[0], complexity_range[1])
        scenarios.append(generate_scenario(complexity=complexity, seed=seed_base + i))
    return scenarios


def scenario_to_brain_input(scenario: dict, rover_pose: tuple = (0.0, 0.0, 0.0)) -> str:
    """Convert a scenario to the text input the brain receives."""
    s = scenario["sensor_readings"]
    parts = [
        f"Scene: {scenario['scene_description']}",
        f"Environment: {scenario['environment_type'].replace('_', ' ')}",
        f"Current goal: search for survivors",
    ]
    if s["audio"]["event"]:
        parts.append(f"Audio detected: {s['audio']['event']['label']} at {s['audio']['db']}dB")
    if scenario["missing_sensors"]:
        parts.append(f"WARNING: {', '.join(scenario['missing_sensors'])} sensors unavailable")
    if scenario["conflicting_data"]:
        parts.append("WARNING: conflicting sensor readings — depth says clear but temperature elevated")
    parts.append(f"Pose: ({rover_pose[0]}, {rover_pose[1]}, {rover_pose[2]}°)")
    return "\n".join(parts)


def evaluate_decision(scenario: dict, tool_calls: list, rover_pose: tuple) -> dict:
    """Evaluate the brain's decisions against the scenario.

    Returns a score 0-1 and per-criterion breakdown.
    """
    criteria = {
        "protocol_adherence": 0.0,
        "hazard_awareness": 0.0,
        "victim_detection": 0.0,
        "communication": 0.0,
        "exploration": 0.0,
    }

    tools_called = {tc["tool"] for tc in tool_calls}

    # Protocol adherence: did it call search_knowledge?
    if "search_knowledge" in tools_called:
        criteria["protocol_adherence"] = 1.0
    elif any(tc["tool"] == "speak" for tc in tool_calls):
        criteria["protocol_adherence"] = 0.5

    # Hazard awareness: did it check temperature/audio/gyro?
    sensor_checks = sum(1 for t in ["get_temperature", "get_audio", "get_gyro"] if t in tools_called)
    if scenario["hazards"]:
        criteria["hazard_awareness"] = min(1.0, sensor_checks / 2.0)
    else:
        criteria["hazard_awareness"] = 1.0  # no hazards, don't need to check

    # Victim detection: did it respond to distress?
    has_distress = scenario["sensor_readings"]["audio"]["event"] is not None
    if has_distress:
        if "speak" in tools_called:
            criteria["victim_detection"] = 1.0
        elif "get_audio" in tools_called:
            criteria["victim_detection"] = 0.5
    else:
        criteria["victim_detection"] = 1.0  # no victims detected, fine

    # Communication: did it speak appropriately?
    speak_calls = [tc for tc in tool_calls if tc["tool"] == "speak"]
    if speak_calls:
        criteria["communication"] = 1.0
    elif has_distress:
        criteria["communication"] = 0.0

    # Exploration: did it move?
    motion_tools = {"forward", "backward", "turn"}
    if motion_tools & tools_called:
        criteria["exploration"] = 1.0
    else:
        criteria["exploration"] = 0.3

    # Overall score
    score = sum(criteria.values()) / len(criteria)

    # Did it log findings?
    logged = "log_finding" in tools_called

    return {
        "score": round(score, 3),
        "criteria": criteria,
        "logged_finding": logged,
        "tools_called": list(tools_called),
        "num_tool_calls": len(tool_calls),
    }


def to_training_jsonl(scenario: dict, tool_calls: list, evaluation: dict) -> dict:
    """Convert a scenario + brain trace into a training example (JSONL format)."""
    return {
        "scenario_id": scenario["id"],
        "environment": scenario["environment_type"],
        "scene_description": scenario["scene_description"],
        "sensor_readings": scenario["sensor_readings"],
        "input": scenario_to_brain_input(scenario),
        "tool_calls": [{"tool": tc["tool"], "args": tc["args"]} for tc in tool_calls],
        "evaluation": evaluation,
        "good": evaluation["score"] >= 0.6,
    }


if __name__ == "__main__":
    # Generate a sample scenario
    s = generate_scenario(complexity=2, seed=42)
    print(json.dumps(s, indent=2))
    print("\n---")
    print(scenario_to_brain_input(s))
