"""Virtual Brain Server: runs the real Backboard brain against a simulated rover
and streams everything to the frontend via WebSocket.

This replaces mock_map_server.py with real AI-driven movement. The brain calls
forward(0.5), the simulated rover moves, the LiDAR reveals the environment
progressively, and the 3D map builds up in real-time.

Run:
    python frontend/virtual_brain_server.py
    # Then: cd frontend && npm run dev
    # Open http://localhost:5173

Requires .env with: BACKBOARD_API_KEY, ELEVENLABS_API_KEY, VOICE_ID
"""

import asyncio
import base64
import json
import logging
import math
import os
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import websockets
from websockets.exceptions import ConnectionClosed
from dotenv import load_dotenv

load_dotenv()

from brain.backboard_client import brain
from brain.tools import SYSTEM_PROMPT, VERBS
from control.mapper import OccupancyMap
from control.telemetry import BrainActivity, SensorState, MissionInsights
from tracking import mongo as db

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("virtual_brain")

# ── Grid config (matches mock_map_server.py) ─────────────────────────────
GRID_SIZE_M = 20.0
RES = 0.2
GW = int(GRID_SIZE_M / RES)
GH = GW
STREAM_HZ = 5

# ── Build true grid (matching DrivingView3D buildings) ─────────────────────
grid = [0.5] * (GW * GH)


def set_cell(col, row, val):
    if 0 <= col < GW and 0 <= row < GH:
        grid[row * GW + col] = val


def fill_rect(cx, cy, w, h, val=0.9):
    for row in range(GH):
        for col in range(GW):
            wx = (col - GW / 2) * RES
            wy = (GH / 2 - row) * RES
            if abs(wx - cx) < w / 2 and abs(wy - cy) < h / 2:
                set_cell(col, row, val)


def fill_circle(cx, cy, r, val=0.85):
    for row in range(GH):
        for col in range(GW):
            wx = (col - GW / 2) * RES
            wy = (GH / 2 - row) * RES
            if math.hypot(wx - cx, wy - cy) < r:
                set_cell(col, row, val)


# Border walls
for i in range(GW):
    set_cell(i, 0, 0.95)
    set_cell(i, GH - 1, 0.95)
    set_cell(0, i, 0.95)
    set_cell(GW - 1, i, 0.95)

# Buildings (matching DrivingView3D)
fill_rect(4, -3, 2, 2)
fill_rect(-3, -5, 1.5, 1.5)
fill_rect(6, 2, 2.5, 2.5)
fill_rect(-5, 3, 1.8, 1.8)
fill_rect(2, -7, 2, 2)
fill_rect(-6, -1, 1.2, 1.2)

# Walls
fill_rect(0, 5, 4, 0.2)
fill_rect(-7, -3, 0.2, 4)

# Rubble
fill_circle(1, 2, 0.6)
fill_circle(-2, -3, 0.8)
fill_circle(5, -1, 0.6)
fill_circle(-4, 4, 0.5)

# Trees
fill_circle(-8, 6, 0.3)
fill_circle(8, -5, 0.3)
fill_circle(-2, 7, 0.3)

# Clear corridor near origin
for row in range(45, 56):
    for col in range(45, 56):
        set_cell(col, row, 0.08)

# ── Progressive LiDAR ─────────────────────────────────────────────────────
true_grid = list(grid)
observed_grid = [0.5] * (GW * GH)
LIDAR_RANGE_M = 4.0
LIDAR_FOV_DEG = 120
LIDAR_RAYS = 48


def world_to_grid(x, y):
    half = GRID_SIZE_M / 2
    return int((x + half) / RES), int((y + half) / RES)


def lidar_sweep(pose):
    x, y, heading = pose
    half_fov = LIDAR_FOV_DEG / 2
    for i in range(LIDAR_RAYS):
        angle = math.radians(heading - half_fov + (LIDAR_FOV_DEG * i / (LIDAR_RAYS - 1)))
        dx, dy = math.cos(angle), math.sin(angle)
        steps = int(LIDAR_RANGE_M / RES)
        for s in range(steps):
            wx = x + dx * s * RES
            wy = y + dy * s * RES
            col, row = world_to_grid(wx, wy)
            row = GH - 1 - row
            if not (0 <= col < GW and 0 <= row < GH):
                break
            idx = row * GW + col
            observed_grid[idx] = true_grid[idx]
            if true_grid[idx] > 0.6:
                break


# ── Static overlay markers ─────────────────────────────────────────────────
sound_sources = [
    {"x": -5.5, "y": 3.5, "kind": "distress", "label": "Help me!", "db": 86},
    {"x": 6.0, "y": -4.5, "kind": "voice", "label": "Is anyone there?", "db": 72},
    {"x": 3.0, "y": 6.5, "kind": "speech", "label": "I'm under the beam", "final": True},
]

heat_points = [
    {"x": 4.0, "y": -3.0, "celsius": 68.0, "status": "overheat"},
    {"x": -5.0, "y": 3.0, "celsius": 42.0, "status": "warm"},
]

hazards = [
    {"x": -2.0, "y": -3.0, "type": "bump"},
    {"x": 5.0, "y": -1.0, "type": "tipped"},
]

annotations = [
    {"x": -5.5, "y": 3.5, "text": "Survivor detected", "source": "gemini"},
    {"x": 1.0, "y": 2.0, "text": "Debris field", "source": "gemini"},
]


# ── Simulated Rover ───────────────────────────────────────────────────────
class SimRover:
    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.heading = 0.0
        self.linear_vel = 0.0
        self.angular_vel = 0.0
        self._lock = threading.Lock()
        self._running = True
        self.temperature = 22.0
        self.audio_db = 35.0
        self.audio_event = None
        self.gyro_pitch = 0.0
        self.gyro_roll = 0.0
        self.gyro_tipped = False
        self.gyro_bump = False
        threading.Thread(target=self._physics, daemon=True).start()

    def _physics(self):
        dt = 0.05
        while self._running:
            with self._lock:
                self.heading += self.angular_vel * dt
                self.x += self.linear_vel * math.cos(math.radians(self.heading)) * dt
                self.y += self.linear_vel * math.sin(math.radians(self.heading)) * dt
            time.sleep(dt)

    def publish_cmd_vel(self, linear, angular):
        with self._lock:
            self.linear_vel = linear
            self.angular_vel = angular

    def get_pose(self):
        with self._lock:
            return (self.x, self.y, self.heading)

    def get_detections(self):
        dets = []
        with self._lock:
            for ox, oy, radius in [(4, -3, 1), (-3, -5, 0.75), (6, 2, 1.25), (-5, 3, 0.9), (2, -7, 1), (-6, -1, 0.6)]:
                dx = ox - self.x
                dy = oy - self.y
                dist = math.sqrt(dx**2 + dy**2)
                if dist < 5.0:
                    bearing = math.degrees(math.atan2(dy, dx)) - self.heading
                    bearing = ((bearing + 180) % 360) - 180
                    dets.append({"label": "obstacle", "distance_m": round(max(0.1, dist - radius), 2), "bearing_deg": round(bearing, 1)})
        return dets

    def read_temperature(self):
        return {"celsius": self.temperature, "status": "ok" if self.temperature < 40 else "warm" if self.temperature < 60 else "overheat"}

    def read_audio(self):
        return {"db": self.audio_db, "event": self.audio_event}

    def read_gyro(self):
        return {"pitch_deg": self.gyro_pitch, "roll_deg": self.gyro_roll, "tipped": self.gyro_tipped, "bump": self.gyro_bump}

    def stop(self):
        self._running = False


# ── Global state ────────────────────────────────────────────────────────────
rover = SimRover()
mapper = OccupancyMap(size_m=GRID_SIZE_M, resolution_m=RES)
brain_activity = BrainActivity()
sensor_state = SensorState()
mission_insights = MissionInsights()
trail = []
brain_events = []
transcript_messages = []  # real transcript from brain speech + STT
last_brain_ts = 0.0
last_pose = (0.0, 0.0, 0.0)
brain_initialized = False
brain_loop_started = False


def execute_tool(name, args):
    """Execute a brain tool call on the simulated rover."""
    pose = rover.get_pose()

    if name == "forward":
        dist = args.get("distance_m", 0.5)
        rover.publish_cmd_vel(0.3, 0.0)
        # Move for a short time then stop
        target_dist = min(dist, 2.0)
        start_x, start_y, _ = pose
        while True:
            cx, cy, _ = rover.get_pose()
            moved = math.sqrt((cx - start_x)**2 + (cy - start_y)**2)
            if moved >= target_dist:
                break
            dets = rover.get_detections()
            ahead = [d for d in dets if abs(d["bearing_deg"]) < 30 and d["distance_m"] < 0.3]
            if ahead:
                rover.publish_cmd_vel(0.0, 0.0)
                result = {"status": "stopped_by_obstacle", "distance_m": ahead[0]["distance_m"]}
                brain_activity.log_call(name, args, result)
                db.log_brain_call(name, args, result, pose)
                return result
            time.sleep(0.05)
        rover.publish_cmd_vel(0.0, 0.0)
        result = {"status": "completed", "distance_m": dist}
        brain_activity.log_call(name, args, result)
        db.log_brain_call(name, args, result, pose)
        return result

    if name == "backward":
        rover.publish_cmd_vel(-0.3, 0.0)
        time.sleep(min(args.get("distance_m", 0.5) / 0.3, 3.0))
        rover.publish_cmd_vel(0.0, 0.0)
        result = {"status": "completed", "distance_m": args.get("distance_m", 0.5)}
        brain_activity.log_call(name, args, result)
        db.log_brain_call(name, args, result, pose)
        return result

    if name == "turn":
        degrees = args.get("degrees", 0)
        rover.publish_cmd_vel(0.0, 60.0 if degrees > 0 else -60.0)
        time.sleep(min(abs(degrees) / 60.0, 3.0))
        rover.publish_cmd_vel(0.0, 0.0)
        result = {"status": "completed", "degrees": degrees}
        brain_activity.log_call(name, args, result)
        db.log_brain_call(name, args, result, pose)
        return result

    if name == "stop":
        rover.publish_cmd_vel(0.0, 0.0)
        result = {"status": "completed"}
        brain_activity.log_call(name, args, result)
        db.log_brain_call(name, args, result, pose)
        return result

    if name == "speak":
        text = args.get("text", "")
        logger.info("[TTS] Rover: %s", text)
        transcript_messages.append({
            "id": f"msg-{len(transcript_messages)}",
            "speaker": "rover",
            "text": text,
            "timestamp": time.strftime("%H:%M:%S"),
        })
        if len(transcript_messages) > 20:
            transcript_messages[:] = transcript_messages[-20:]
        try:
            from voice.tts import speak
            speak(text)
        except Exception:
            pass

        # Simulate victim response after a short delay
        victim_responses = [
            "Help me! I'm trapped under the rubble!",
            "I can hear you! Please come closer!",
            "I'm injured but I can move. Where are you?",
            "Thank god someone is here. I'm over here!",
            "I've been here for hours. Can you find me?",
            "My leg is stuck. I can't move it.",
        ]
        import random
        victim_text = random.choice(victim_responses)

        def victim_responds():
            time.sleep(3.0)
            logger.info("[TTS] Victim: %s", victim_text)
            transcript_messages.append({
                "id": f"msg-{len(transcript_messages)}",
                "speaker": "person",
                "text": victim_text,
                "timestamp": time.strftime("%H:%M:%S"),
            })
            if len(transcript_messages) > 20:
                transcript_messages[:] = transcript_messages[-20:]
            try:
                from voice.tts import speak_as_victim
                speak_as_victim(victim_text)
            except Exception:
                pass
            # Feed victim response back to brain as a new user command
            global last_brain_ts, last_pose
            last_brain_ts = 0.0  # trigger immediate brain call
            logger.info("Victim responded — triggering brain to react")

        threading.Thread(target=victim_responds, daemon=True).start()

        result = {"status": "completed"}
        brain_activity.log_call(name, args, result)
        db.log_brain_call(name, args, result, pose)
        return result

    if name == "look_around":
        dets = rover.get_detections()
        scene = f"{len(dets)} obstacles nearby" if dets else "open space ahead"
        result = {"scene": scene}
        brain_activity.log_call(name, args, result)
        db.log_brain_call(name, args, result, pose)
        return result

    if name == "check_map":
        result = mapper.nearby_summary(pose, args.get("radius_m", 3.0))
        brain_activity.log_call(name, args, result)
        db.log_brain_call(name, args, result, pose)
        return result

    if name == "check_safety":
        dets = rover.get_detections()
        action = args.get("action", "")
        if action == "forward":
            ahead = [d for d in dets if abs(d["bearing_deg"]) < 30 and d["distance_m"] < 0.4]
            if ahead:
                result = {"status": "VETO", "action": action, "reason": "obstacle ahead"}
                brain_activity.log_call(name, args, result)
                db.log_brain_call(name, args, result, pose)
                return result
        result = {"status": "OK", "action": action}
        brain_activity.log_call(name, args, result)
        db.log_brain_call(name, args, result, pose)
        return result

    if name == "search_knowledge":
        result = brain.search_memory(args.get("query", ""))
        brain_activity.log_call(name, args, result or {"results": "no results"})
        db.log_rag(args.get("query", ""), result or {"results": "no results"}, pose)
        db.log_brain_call(name, args, result or {"results": "no results"}, pose)
        return result or {"results": "no results"}

    if name == "log_finding":
        result = brain.log_finding(args.get("finding_type", ""), args.get("description", ""))
        db.log_finding(args.get("finding_type", ""), args.get("description", ""), pose)
        brain_activity.log_call(name, args, result or {"status": "logged"})
        db.log_brain_call(name, args, result or {"status": "logged"}, pose)
        return result or {"status": "logged"}

    if name == "analyze_patterns":
        result = brain.get_insights()
        if result:
            mission_insights.update(result)
            db.log_insights(result)
        brain_activity.log_call(name, args, result or {"insights": "no data"})
        db.log_brain_call(name, args, result or {"insights": "no data"}, pose)
        return result or {"insights": "no data"}

    if name == "get_obstacles":
        result = {"detections": rover.get_detections()}
        brain_activity.log_call(name, args, result)
        db.log_brain_call(name, args, result, pose)
        return result

    if name == "get_state":
        result = {"pose": rover.get_pose(), "velocity": (rover.linear_vel, rover.angular_vel), "goal": None}
        brain_activity.log_call(name, args, result)
        db.log_brain_call(name, args, result, pose)
        return result

    if name == "get_temperature":
        temp = rover.read_temperature()
        sensor_state.update_temperature(temp["celsius"], temp["status"])
        brain_activity.log_call(name, args, temp)
        db.log_brain_call(name, args, temp, pose)
        return temp

    if name == "get_audio":
        audio = rover.read_audio()
        sensor_state.update_audio(audio.get("db", 0), audio.get("event"))
        brain_activity.log_call(name, args, audio)
        db.log_brain_call(name, args, audio, pose)
        return audio

    if name == "get_gyro":
        gyro = rover.read_gyro()
        sensor_state.update_gyro(gyro.get("pitch_deg", 0), gyro.get("roll_deg", 0), gyro.get("tipped", False), gyro.get("bump", False))
        brain_activity.log_call(name, args, gyro)
        db.log_brain_call(name, args, gyro, pose)
        return gyro

    result = {"status": "error", "detail": f"unknown verb {name}"}
    brain_activity.log_call(name, args, result)
    return result


async def run_brain_episode(command="search for survivors"):
    """Run one brain episode — the real Backboard brain reasons and calls tools."""
    global last_brain_ts, last_pose

    pose = rover.get_pose()
    dets = rover.get_detections()
    scene = f"{len(dets)} obstacles nearby, closest at {min(d['distance_m'] for d in dets):.1f}m" if dets else "open space ahead"

    user_content = (
        f"Scene: {scene}\n"
        f"Current goal: search for survivors in hazardous area\n"
        f"User command: {command}\n"
        f"Pose: ({pose[0]:.1f}, {pose[1]:.1f}, {pose[2]:.0f}°)"
    )

    logger.info("Brain episode: %s", command)

    try:
        results = await brain._run_tools(
            content=user_content,
            system_prompt=SYSTEM_PROMPT,
            tools=VERBS,
            execute_tool=execute_tool,
            memory="Auto",
        )

        for r in results:
            brain_events.append({
                "tool": r["name"],
                "args": r["arguments"],
                "result": r["result"],
                "timestamp": time.time(),
            })
            if len(brain_events) > 20:
                brain_events[:] = brain_events[-20:]

        logger.info("Brain made %d tool calls", len(results))
    except Exception as e:
        logger.warning("Brain episode failed: %s", e)

    last_brain_ts = time.time()
    last_pose = rover.get_pose()


async def brain_loop():
    """Background loop that runs brain episodes with rate limiting."""
    global brain_initialized

    # Initialize brain (RAG upload, encounters)
    logger.info("Initializing brain (RAG upload, encounters)...")
    try:
        await brain._ensure_initialized()
        brain_initialized = True
        logger.info("Brain initialized — RAG uploaded, encounters loaded")
    except Exception as e:
        logger.warning("Brain init failed: %s", e)

    # First episode
    await run_brain_episode("search for survivors")

    # Subsequent episodes — rate limited
    while True:
        await asyncio.sleep(5)
        pose = rover.get_pose()
        moved = math.sqrt((pose[0] - last_pose[0])**2 + (pose[1] - last_pose[1])**2)
        elapsed = time.time() - last_brain_ts

        # Trigger brain if: moved significantly, or 30s periodic
        if moved > 1.0 or elapsed > 30:
            await run_brain_episode("continue searching")


async def handler(websocket):
    """WebSocket handler — streams map + brain activity + sensors to frontend.
    Also receives rating messages from the frontend for TTS evaluation."""
    print(f"[virtual-brain] frontend connected: {websocket.remote_address}")

    # Start brain loop in background if not already running
    global brain_loop_started
    if not brain_loop_started:
        brain_loop_started = True
        asyncio.create_task(brain_loop())

    period = 1.0 / STREAM_HZ
    while True:
        # Check for incoming rating messages (non-blocking)
        try:
            msg = await asyncio.wait_for(websocket.recv(), timeout=0.01)
            data = json.loads(msg)
            if data.get("type") == "rating":
                rating = data.get("rating")
                logger.info("TTS rating received: %s for text id %s", rating, data.get("id"))
                db._insert("tts_ratings", {
                    "rating": rating,
                    "text_id": data.get("id"),
                    "timestamp": time.time(),
                })
        except (asyncio.TimeoutError, json.JSONDecodeError, ConnectionClosed):
            pass

        pose = rover.get_pose()

        # Update trail
        trail.append([pose[0], pose[1]])
        if len(trail) > 300:
            trail[:] = trail[-300:]

        # LiDAR sweep
        lidar_sweep(pose)

        # Build payload
        grid_arr = np.array(observed_grid, dtype=np.float32)
        grid_uint8 = np.clip(grid_arr * 255, 0, 255).astype(np.uint8)
        grid_b64 = base64.b64encode(grid_uint8.tobytes()).decode("ascii")

        # Update sensor state
        temp = rover.read_temperature()
        audio = rover.read_audio()
        gyro = rover.read_gyro()
        sensor_state.update_temperature(temp["celsius"], temp["status"])
        sensor_state.update_audio(audio.get("db", 0), audio.get("event"))
        sensor_state.update_gyro(gyro.get("pitch_deg", 0), gyro.get("roll_deg", 0), gyro.get("tipped", False), gyro.get("bump", False))

        payload = {
            "rover_pose": [pose[0], pose[1], pose[2]],
            "grid": grid_b64,
            "grid_encoding": "base64_uint8",
            "grid_width": GW,
            "grid_height": GH,
            "grid_resolution_m": RES,
            "sound_sources": sound_sources,
            "heat_points": heat_points,
            "hazards": hazards,
            "annotations": annotations,
            "trail": list(trail),
            "brain_activity": brain_events[-10:],
            "sensor_state": sensor_state.snapshot(),
            "insights": mission_insights.get(),
            "transcript": transcript_messages[-10:],
        }

        await websocket.send(json.dumps(payload, default=str))
        await asyncio.sleep(period)


async def main():
    print("=" * 60)
    print("VIRTUAL BRAIN SERVER — Real Backboard brain + 3D simulation")
    print("=" * 60)
    print(f"WebSocket: ws://0.0.0.0:8766")
    print(f"Frontend: http://localhost:5173 (run: cd frontend && npm run dev)")
    print(f"Brain model: gemini-3.5-flash (via Backboard)")
    print(f"Tools: {len(VERBS)} verbs")
    print(f"RAG: rescue_protocols.md + encounter_history.md")
    print(f"MongoDB: {'connected' if db.get_stats().get('connected') else 'disabled'}")
    print()

    async with websockets.serve(handler, "0.0.0.0", 8766):
        await asyncio.Future()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        rover.stop()
        print("\nVirtual brain server stopped.")
