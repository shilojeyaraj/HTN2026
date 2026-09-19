"""Level 3 autonomy test: run the real Backboard brain against a simulated rover.

This tests the full autonomous loop with real API calls:
  - Backboard agent loop (Gemini Pro) with 16 tools
  - RAG knowledge base retrieval (rescue protocols + encounter history)
  - Structured mission memory (log_finding, search_knowledge, analyze_patterns)
  - Inner Monologue (real execution results fed back)
  - Teammate tools (look_around, check_map, check_safety)

No hardware needed. Requires real API keys in .env:
  BACKBOARD_API_KEY, BASETEN_API_KEY, BASETEN_PARSER_MODEL_ID,
  ELEVENLABS_API_KEY, VOICE_ID

Run:
    python tests/test_autonomy.py
    python tests/test_autonomy.py --command "search for survivors"
    python tests/test_autonomy.py --episodes 5
"""

import argparse
import asyncio
import json
import logging
import math
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

from brain.backboard_client import brain
from brain.tools import SYSTEM_PROMPT, VERBS
from control.mapper import OccupancyMap
from control.pose import PoseEstimator

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("autonomy_test")


class SimRover:
    """Simple velocity-controlled simulated rover for testing the brain."""

    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.heading = 0.0
        self.linear_vel = 0.0
        self.angular_vel = 0.0
        self._lock = threading.Lock()
        self._running = True

        # Simulated obstacles at known positions (x, y, radius)
        self.obstacles = [
            (1.5, 0.5, 0.3),
            (2.5, 1.5, 0.25),
            (1.0, 2.0, 0.2),
        ]

        # Simulated sensor state
        self.temperature = 22.0
        self.audio_db = 35.0
        self.audio_event = None
        self.gyro_pitch = 0.0
        self.gyro_roll = 0.0
        self.gyro_tipped = False
        self.gyro_bump = False

        # Start physics thread
        threading.Thread(target=self._physics, daemon=True).start()

    def _physics(self):
        dt = 0.05
        while self._running:
            with self._lock:
                self.heading += self.angular_vel * dt
                self.x += self.linear_vel * math.cos(math.radians(self.heading)) * dt
                self.y += self.linear_vel * math.sin(math.radians(self.heading)) * dt
            time.sleep(dt)

    def publish_cmd_vel(self, linear: float, angular: float):
        with self._lock:
            self.linear_vel = linear
            self.angular_vel = angular

    def get_state(self):
        with self._lock:
            return {"x": round(self.x, 2), "y": round(self.y, 2), "heading_deg": round(self.heading, 1)}

    def get_pose(self):
        with self._lock:
            return (self.x, self.y, self.heading)

    def get_detections(self):
        """Return simulated obstacle detections within sensor range."""
        dets = []
        with self._lock:
            for ox, oy, radius in self.obstacles:
                dx = ox - self.x
                dy = oy - self.y
                dist = math.sqrt(dx ** 2 + dy ** 2)
                if dist < 3.0:
                    bearing = math.degrees(math.atan2(dy, dx)) - self.heading
                    bearing = ((bearing + 180) % 360) - 180
                    dets.append({
                        "label": "obstacle",
                        "distance_m": round(dist - radius, 2),
                        "bearing_deg": round(bearing, 1),
                    })
        return dets

    def read_temperature(self):
        return {"celsius": self.temperature, "status": "ok" if self.temperature < 40 else "warm" if self.temperature < 60 else "overheat"}

    def read_audio(self):
        return {"db": self.audio_db, "event": self.audio_event}

    def read_gyro(self):
        return {"pitch_deg": self.gyro_pitch, "roll_deg": self.gyro_roll, "tipped": self.gyro_tipped, "bump": self.gyro_bump}

    def set_heat(self, celsius):
        self.temperature = celsius

    def set_distress(self):
        self.audio_db = 85
        self.audio_event = {"kind": "distress", "label": "help me", "bearing_deg": 0}

    def stop(self):
        self._running = False


def run_autonomy_test(command="search for survivors", episodes=3):
    """Run the real Backboard brain against a simulated rover."""
    asyncio.run(_async_autonomy_test(command, episodes))


async def _async_autonomy_test(command, episodes):
    """Async implementation — runs all episodes in one event loop."""
    print("=" * 70)
    print("LEVEL 3 AUTONOMY TEST — Real Backboard brain vs simulated rover")
    print("=" * 70)
    print(f"\nCommand: \"{command}\"")
    print(f"Episodes: {episodes}")
    print(f"Tools available: {len(VERBS)} verbs")
    print(f"  Motion: forward, backward, turn, stop")
    print(f"  Voice: speak")
    print(f"  Sensors: get_obstacles, get_state, get_temperature, get_audio, get_gyro")
    print(f"  Teammates: look_around, check_map, check_safety")
    print(f"  Knowledge: search_knowledge, log_finding, analyze_patterns")
    print()

    rover = SimRover()
    mapper = OccupancyMap(size_m=6.0, resolution_m=0.1)
    pose_est = PoseEstimator()

    for ep in range(episodes):
        print(f"\n{'─' * 70}")
        print(f"EPISODE {ep + 1}/{episodes}")
        print(f"{'─' * 70}")

        pose = rover.get_pose()
        state = rover.get_state()
        dets = rover.get_detections()

        # Build the user content for the brain
        scene = "Open space ahead" if not dets else f"{len(dets)} obstacles nearby, closest at {min(d['distance_m'] for d in dets):.1f}m"
        user_content = (
            f"Scene: {scene}\n"
            f"Current goal: search for survivors in hazardous area\n"
            f"User command: {command if ep == 0 else 'continue searching'}\n"
            f"Pose: ({state['x']}, {state['y']}, {state['heading_deg']}°)"
        )

        print(f"\n  [INPUT] {user_content.replace(chr(10), ' | ')}")

        # Run the real Backboard brain (call async method directly)
        print(f"\n  [BRAIN] Calling Backboard (Gemini Pro) with {len(VERBS)} tools...")

        def execute_tool(name, args):
            return execute_tool_sync(name, args, rover, mapper, pose_est)

        results = await brain._run_tools(
            content=user_content,
            system_prompt=SYSTEM_PROMPT,
            tools=VERBS,
            execute_tool=execute_tool,
            memory="Auto",
        )

        print(f"\n  [RESULTS] Brain made {len(results)} tool call(s):")
        for i, r in enumerate(results):
            print(f"    {i + 1}. {r['name']}({json.dumps(r['arguments'])})")
            print(f"       → {json.dumps(r['result'])}")

        # Update map
        pose = rover.get_pose()
        mapper.add_trail(pose)
        for d in dets:
            mapper.add_depth(pose, d["bearing_deg"], max(0.0, 1.0 - d["distance_m"] / 3.0))
        if rover.audio_event:
            mapper.add_sound(pose, rover.audio_event["kind"], rover.audio_event.get("label", ""), rover.audio_db)
        temp = rover.read_temperature()
        mapper.add_heat(pose, temp["celsius"], temp["status"])

        print(f"\n  [MAP] Trail: {len(mapper.trail)} points, "
              f"Rover at ({state['x']}, {state['y']}, {state['heading_deg']}°)")

        # Simulate finding a distress call in episode 2
        if ep == 1:
            print("\n  [SIM] Simulating distress call detected!")
            rover.set_distress()
        if ep == 2:
            print("\n  [SIM] Simulating heat source detected!")
            rover.set_heat(72.0)

    print(f"\n{'=' * 70}")
    print("AUTONOMY TEST COMPLETE")
    print(f"{'=' * 70}")
    print(f"Final rover pose: {rover.get_state()}")
    print(f"Map trail points: {len(mapper.trail)}")
    rover.stop()


def execute_tool_sync(name, args, rover, mapper, pose_est):
    """Execute a brain tool call on the simulated rover."""
    pose = rover.get_pose()

    if name == "forward":
        dist = args.get("distance_m", 0.5)
        dets = rover.get_detections()
        ahead = [d for d in dets if abs(d["bearing_deg"]) < 30 and d["distance_m"] < 0.3]
        if ahead:
            return {"status": "stopped_by_obstacle", "distance_m": ahead[0]["distance_m"]}
        return {"status": "completed", "distance_m": dist}

    if name == "backward":
        return {"status": "completed", "distance_m": args.get("distance_m", 0.5)}

    if name == "turn":
        return {"status": "completed", "degrees": args.get("degrees", 0)}

    if name == "stop":
        return {"status": "completed"}

    if name == "speak":
        print(f"\n  [TTS] {args.get('text', '')}")
        return {"status": "completed"}

    if name == "look_around":
        dets = rover.get_detections()
        if dets:
            scene = f"Obstacles detected: {len(dets)} nearby. "
            scene += f"Closest at {min(d['distance_m'] for d in dets):.1f}m bearing {min(d['bearing_deg'] for d in dets):.0f}°."
        else:
            scene = "Open space ahead, no obstacles within sensor range."
        return {"scene": scene}

    if name == "check_map":
        return mapper.nearby_summary(pose, args.get("radius_m", 3.0))

    if name == "check_safety":
        dets = rover.get_detections()
        action = args.get("action", "")
        if action == "forward":
            ahead = [d for d in dets if abs(d["bearing_deg"]) < 30 and d["distance_m"] < 0.4]
            if ahead:
                return {"status": "VETO", "action": action, "reason": "obstacle ahead"}
        return {"status": "OK", "action": action}

    if name == "search_knowledge":
        result = brain.search_memory(args.get("query", ""))
        print(f"\n  [RAG] query: {args.get('query', '')}")
        if result:
            print(f"  [RAG] result: {json.dumps(result, indent=2)[:500]}")
        return result or {"results": "no results found"}

    if name == "log_finding":
        result = brain.log_finding(args.get("finding_type", ""), args.get("description", ""))
        print(f"\n  [MEMORY] logged: [{args.get('finding_type', '')}] {args.get('description', '')}")
        return result or {"status": "logged"}

    if name == "analyze_patterns":
        result = brain.get_insights()
        print(f"\n  [INSIGHTS] {json.dumps(result, indent=2)[:500] if result else 'no insights yet'}")
        return result or {"insights": "no data yet"}

    if name == "get_obstacles":
        return {"detections": rover.get_detections()}

    if name == "get_state":
        return {"pose": rover.get_pose(), "velocity": (rover.linear_vel, rover.angular_vel), "goal": None}

    if name == "get_temperature":
        return rover.read_temperature()

    if name == "get_audio":
        return rover.read_audio()

    if name == "get_gyro":
        return rover.read_gyro()

    return {"status": "error", "detail": f"unknown verb {name}"}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Level 3 autonomy test")
    ap.add_argument("--command", default="search for survivors", help="initial voice command")
    ap.add_argument("--episodes", type=int, default=3, help="number of brain episodes")
    args = ap.parse_args()
    run_autonomy_test(command=args.command, episodes=args.episodes)
