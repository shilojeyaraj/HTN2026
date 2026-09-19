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

# ── build a static obstacle field ─────────────────────────────────────────
# 0.5 = unknown, 0.0 = free, 1.0 = occupied
grid = [0.5] * (GW * GH)


def set_cell(col: int, row: int, val: float) -> None:
    if 0 <= col < GW and 0 <= row < GH:
        grid[row * GW + col] = val


def world_to_grid(x: float, y: float) -> tuple[int, int]:
    half = GRID_SIZE_M / 2
    return int((x + half) / RES), int((y + half) / RES)


# border walls
for i in range(GW):
    set_cell(i, 0, 0.95)
    set_cell(i, GH - 1, 0.95)
    set_cell(0, i, 0.95)
    set_cell(GW - 1, i, 0.95)

# interior wall 1 (horizontal)
for i in range(20, 60):
    set_cell(i, 35, 0.92)
# gap in the wall
for i in range(38, 42):
    set_cell(i, 35, 0.1)

# interior wall 2 (vertical)
for i in range(50, 80):
    set_cell(65, i, 0.93)
for i in range(60, 66):
    set_cell(65, i, 0.1)

# scattered debris clumps
for cx, cy, r in [
    (-6, 3, 2), (5, -5, 3), (-3, -6, 2), (7, 6, 2), (2, 7, 1),
]:
    for row in range(GH):
        for col in range(GW):
            wx = (col - GW / 2) * RES
            wy = (GH / 2 - row) * RES
            if math.hypot(wx - cx, wy - cy) < r * 0.6:
                set_cell(col, row, 0.88)
            elif math.hypot(wx - cx, wy - cy) < r:
                if grid[row * GW + col] == 0.5:
                    set_cell(col, row, 0.15)

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
    {"x": -4.0, "y": -5.5, "celsius": 68.0, "status": "overheat"},
    {"x": 5.5, "y": 5.0, "celsius": 42.0, "status": "warm"},
]

hazards = [
    {"x": -2.0, "y": 1.0, "type": "bump"},
    {"x": 4.0, "y": -2.5, "type": "tipped"},
]

annotations = [
    {"x": -5.5, "y": 3.5, "text": "Survivor detected", "source": "gemini"},
    {"x": 0.5, "y": -6.0, "text": "Debris field", "source": "gemini"},
]


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


async def handler(websocket):
    print(f"[mock-map] frontend connected: {websocket.remote_address}")
    t0 = time.time()
    while True:
        t = time.time() - t0
        pose = rover_pose(t)

        # append trail
        trail.append([pose[0], pose[1]])
        if len(trail) > 300:
            trail[:] = trail[-300:]

        grid_arr = np.array(grid, dtype=np.float32)
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
