"""Mock WebSocket server that streams a fake MapPayload to the frontend.

Lets you test the 3D three.js map view without any Pi or robot hardware.

Usage:
    cd frontend
    python mock_map_server.py

Then open http://localhost:5173 in your browser (run `npm run dev` first).
The frontend connects to ws://localhost:8766 automatically.
"""

import asyncio
import base64
import json
import math
import time

import numpy as np

import websockets

# ── grid config (matches control/mapper.py defaults) ────────────────────
GRID_SIZE_M = 20.0
RES = 0.2
GW = int(GRID_SIZE_M / RES)  # 100
GH = GW
STREAM_HZ = 5

# ── build obstacle field matching DrivingView3D buildings ──────────────────
# 0.5 = unknown, 0.0 = free, 1.0 = occupied
grid = [0.5] * (GW * GH)


def set_cell(col: int, row: int, val: float) -> None:
    if 0 <= col < GW and 0 <= row < GH:
        grid[row * GW + col] = val


def world_to_grid(x: float, y: float) -> tuple[int, int]:
    half = GRID_SIZE_M / 2
    return int((x + half) / RES), int((y + half) / RES)


def fill_rect(cx: float, cy: float, w: float, h: float, val: float = 0.9) -> None:
    """Fill a rectangular region in the grid centered at (cx, cy) with size (w, h)."""
    for row in range(GH):
        for col in range(GW):
            wx = (col - GW / 2) * RES
            wy = (GH / 2 - row) * RES
            if abs(wx - cx) < w / 2 and abs(wy - cy) < h / 2:
                set_cell(col, row, val)


def fill_circle(cx: float, cy: float, r: float, val: float = 0.85) -> None:
    """Fill a circular region in the grid centered at (cx, cy) with radius r."""
    for row in range(GH):
        for col in range(GW):
            wx = (col - GW / 2) * RES
            wy = (GH / 2 - row) * RES
            if math.hypot(wx - cx, wy - cy) < r:
                set_cell(col, row, val)


# border walls
for i in range(GW):
    set_cell(i, 0, 0.95)
    set_cell(i, GH - 1, 0.95)
    set_cell(0, i, 0.95)
    set_cell(GW - 1, i, 0.95)

# Buildings (matching DrivingView3D positions)
fill_rect(4, -3, 2, 2)       # building [4, -3]
fill_rect(-3, -5, 1.5, 1.5)  # building [-3, -5]
fill_rect(6, 2, 2.5, 2.5)    # building [6, 2]
fill_rect(-5, 3, 1.8, 1.8)   # building [-5, 3]
fill_rect(2, -7, 2, 2)       # building [2, -7]
fill_rect(-6, -1, 1.2, 1.2)  # building [-6, -1]

# Walls
fill_rect(0, 5, 4, 0.2)     # wall [0, 5]
fill_rect(-7, -3, 0.2, 4)    # wall [-7, -3]

# Rubble piles (matching DrivingView3D)
fill_circle(1, 2, 0.6)
fill_circle(-2, -3, 0.8)
fill_circle(5, -1, 0.6)
fill_circle(-4, 4, 0.5)

# Trees (small obstacles)
fill_circle(-8, 6, 0.3)
fill_circle(8, -5, 0.3)
fill_circle(-2, 7, 0.3)

# clear a corridor near origin
for row in range(45, 56):
    for col in range(45, 56):
        set_cell(col, row, 0.08)

# ── static overlay markers ────────────────────────────────────────────────
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


# ── progressive LiDAR mapping ─────────────────────────────────────────────
# `grid` above is the TRUE environment. The rover only sees what its LiDAR
# has swept, so we keep a separate observed grid that starts fully unknown
# (0.5) and fills in as rays from the rover reveal cells.
true_grid = list(grid)
observed_grid = [0.5] * (GW * GH)
LIDAR_RANGE_M = 4.0
LIDAR_FOV_DEG = 120
LIDAR_RAYS = 48


def lidar_sweep(pose: tuple[float, float, float]) -> None:
    """Ray-cast from the rover into the true grid, revealing cells into observed_grid."""
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
            # match the row flip used when building the true grid
            row = GH - 1 - row
            if not (0 <= col < GW and 0 <= row < GH):
                break
            idx = row * GW + col
            observed_grid[idx] = true_grid[idx]
            if true_grid[idx] > 0.6:
                break  # ray blocked by obstacle


# ── simulate rover movement (figure-8) ────────────────────────────────────
def rover_pose(t: float) -> tuple[float, float, float]:
    """Figure-8 path centered at origin, ~8m wide."""
    omega = 0.15
    x = 4.0 * math.sin(omega * t)
    y = 4.0 * math.sin(omega * t * 2) * 0.5
    # heading = tangent direction
    dx = 4.0 * omega * math.cos(omega * t)
    dy = 4.0 * omega * 2 * math.cos(omega * t * 2) * 0.5
    heading = math.degrees(math.atan2(dy, dx))
    return x, y, heading


trail: list[list[float]] = []


# ── simulate brain activity ───────────────────────────────────────────────
brain_events = []
event_idx = 0

SIM_EVENTS = [
    ("search_knowledge", {"query": "search pattern"}, {"results": "Lawn-mowing pattern recommended for area coverage"}),
    ("forward", {"distance_m": 0.5}, {"status": "completed"}),
    ("get_obstacles", {}, {"detections": [{"distance_m": 1.3, "bearing_deg": 0}]}),
    ("check_safety", {"action": "forward"}, {"status": "OK"}),
    ("forward", {"distance_m": 1.0}, {"status": "completed"}),
    ("get_temperature", {}, {"celsius": 38.5, "status": "warm"}),
    ("speak", {"text": "Temperature rising, continuing search"}, {"status": "completed"}),
    ("search_knowledge", {"query": "thermal hazard approach"}, {"results": "Stop, announce temperature, find alternate route"}),
    ("turn", {"degrees": 45}, {"status": "completed"}),
    ("get_audio", {}, {"db": 85, "event": {"kind": "distress", "label": "help me"}}),
    ("speak", {"text": "I hear you. I'm a rescue rover. Help is on the way."}, {"status": "completed"}),
    ("log_finding", {"finding_type": "survivor", "description": "distress call at (2.3, 1.1)"}, {"status": "logged"}),
    ("check_map", {"radius_m": 3.0}, {"obstacles_nearby": 2, "sounds_nearby": 1}),
    ("analyze_patterns", {}, {"rescue_rate": "50%", "avg_duration": "65 min", "best_location": "public infrastructure 75%"}),
    ("forward", {"distance_m": 0.5}, {"status": "completed"}),
    ("log_finding", {"finding_type": "area_explored", "description": "north corridor cleared"}, {"status": "logged"}),
]

sim_insights = {
    "rescue_rate": "50% (4 of 8 encounters)",
    "avg_duration": "65 minutes (rescued)",
    "best_location_type": "Public infrastructure 75%",
    "residential_rate": "33% (1 of 3)",
    "total_encounters": "8",
    "pattern": "Longer encounters correlate with rescue success",
}


async def handler(websocket):
    print(f"[mock-map] frontend connected: {websocket.remote_address}")
    t0 = time.time()
    event_timer = 0
    while True:
        t = time.time() - t0
        pose = rover_pose(t)

        # append trail
        trail.append([pose[0], pose[1]])
        if len(trail) > 300:
            trail[:] = trail[-300:]

        # LiDAR sweep reveals the environment progressively
        lidar_sweep(pose)

        # emit a brain event every ~1.5s
        if t - event_timer > 1.5:
            global event_idx
            if event_idx < len(SIM_EVENTS):
                tool, args, result = SIM_EVENTS[event_idx]
                brain_events.append({
                    "tool": tool,
                    "args": args,
                    "result": result,
                    "timestamp": time.time(),
                })
                event_idx += 1
                event_timer = t
            else:
                # loop back
                event_idx = 0
                event_timer = t

        # simulate sensor state
        temp_c = 38.5 + 5.0 * math.sin(t * 0.2)
        temp_status = "overheat" if temp_c >= 60 else "warm" if temp_c >= 40 else "ok"
        db_val = 35.0 + 20.0 * abs(math.sin(t * 0.3))
        audio_event = {"kind": "distress", "label": "help me"} if db_val > 80 else None
        pitch = 5.0 * math.sin(t * 0.5)
        roll = 3.0 * math.cos(t * 0.4)

        sensor_snapshot = {
            "temperature": {"celsius": round(temp_c, 1), "status": temp_status},
            "audio": {"db": round(db_val, 1), "event": audio_event},
            "gyro": {"pitch_deg": round(pitch, 1), "roll_deg": round(roll, 1), "tipped": False, "bump": False},
        }

        grid_arr = np.array(observed_grid, dtype=np.float32)
        grid_uint8 = np.clip(grid_arr * 255, 0, 255).astype(np.uint8)
        grid_b64 = base64.b64encode(grid_uint8.tobytes()).decode("ascii")

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
            "sensor_state": sensor_snapshot,
            "insights": sim_insights if t > 5 else None,
        }
        await websocket.send(json.dumps(payload))
        await asyncio.sleep(1.0 / STREAM_HZ)


async def main():
    print(f"[mock-map] WebSocket server listening on ws://0.0.0.0:8766")
    print("[mock-map] Start the frontend with:  cd frontend && npm run dev")
    print("[mock-map] Then open http://localhost:5173")
    async with websockets.serve(handler, "0.0.0.0", 8766):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
