"""End-to-end latency test: sensor reading → occupancy map → WebSocket → frontend
receive.

Measures the time from a sensor detection entering the mapper to the frontend
receiving a renderable JSON payload. Runs 100 iterations and reports per-stage
statistics. Uses a direct echo WebSocket server to isolate transport latency
from the 5 Hz stream throttle.

Usage:
    cd /Users/shilojeyaraj/VScode/htn2026/HTN2026-frontend
    PYTHONPATH=. python3 tests/test_map_latency.py

    # or via pytest:
    PYTHONPATH=. pytest tests/test_map_latency.py -v -s
"""

import asyncio
import json
import math
import statistics
import time

import numpy as np
import websockets

from control.mapper import OccupancyMap
from control.map_server import STREAM_HZ


# ── helpers ─────────────────────────────────────────────────────────────

def make_map(size_m=20.0, res=0.2) -> OccupancyMap:
    return OccupancyMap(size_m=size_m, resolution_m=res)


def simulate_sensor_sweep(m: OccupancyMap, pose: tuple, tick: int) -> None:
    """Simulate one tick of sensor readings entering the mapper."""
    # ultrasonic: 3 rays at different bearings
    for bearing in [-15, 0, 15]:
        dist = 1.5 + 0.5 * math.sin(tick * 0.3 + bearing)
        m.add_ultrasonic(pose, bearing_deg=bearing, distance_m=dist)
    # camera depth: 3 proximity readings
    for bearing in [-30, 0, 30]:
        prox = 0.4 + 0.2 * math.cos(tick * 0.2 + bearing)
        m.add_depth(pose, bearing_deg=bearing, proximity=prox)
    # audio event every 10 ticks
    if tick % 10 == 0:
        m.add_sound(pose, kind="distress", label="help!", db=85.0)
    # heat every 20 ticks
    if tick % 20 == 0:
        m.add_heat(pose, celsius=55.0, status="warm")
    # hazard every 50 ticks
    if tick % 50 == 0:
        m.add_hazard(pose, "bump")
    # annotation every 25 ticks
    if tick % 25 == 0:
        m.add_annotation(pose, "obstacle ahead", "gemini")
    # trail every tick
    m.add_trail(pose)


def rover_pose_at(tick: int) -> tuple:
    """Simulated rover pose moving in a circle."""
    angle = tick * 0.05
    r = 3.0
    x = r * math.cos(angle)
    y = r * math.sin(angle)
    heading = math.degrees(angle + math.pi / 2)
    return (x, y, heading)


# ── echo server (measures pure WebSocket transport) ──────────────────────

async def echo_handler(websocket):
    """Echo back any received message immediately."""
    async for msg in websocket:
        await websocket.send(msg)


async def start_echo_server(port: int) -> tuple:
    """Start an echo WebSocket server, return (server_obj, stop_fn)."""
    server = await websockets.serve(echo_handler, "127.0.0.1", port)
    async def stop():
        server.close()
        await server.wait_closed()
    return server, stop


# ── stage timing ──────────────────────────────────────────────────────────

class LatencyResults:
    def __init__(self):
        self.sensor_ms: list[float] = []
        self.payload_ms: list[float] = []
        self.json_ms: list[float] = []
        self.ws_transport_ms: list[float] = []  # pure WebSocket round-trip
        self.backend_total_ms: list[float] = []  # sensor → JSON ready to send
        self.full_pipeline_ms: list[float] = []  # sensor → client received JSON

    def add(self, sensor, payload, json_t, ws_transport, backend_total, full_pipeline):
        self.sensor_ms.append(sensor)
        self.payload_ms.append(payload)
        self.json_ms.append(json_t)
        self.ws_transport_ms.append(ws_transport)
        self.backend_total_ms.append(backend_total)
        self.full_pipeline_ms.append(full_pipeline)

    def report(self, name: str, values: list[float]) -> str:
        if not values:
            return f"  {name:35s}  no data"
        med = statistics.median(values)
        p95 = sorted(values)[int(len(values) * 0.95)] if len(values) > 1 else values[0]
        mn = min(values)
        mx = max(values)
        return f"  {name:35s}  median {med:7.2f} ms   p95 {p95:7.2f} ms   min {mn:7.2f} ms   max {mx:7.2f} ms"

    def summary(self) -> str:
        lines = ["", "═" * 76, "  LATENCY BREAKDOWN (sensor detection → frontend render)", "═" * 76]
        lines.append(self.report("1. sensor → mapper ray-cast", self.sensor_ms))
        lines.append(self.report("2. mapper.to_payload()", self.payload_ms))
        lines.append(self.report("3. json.dumps()", self.json_ms))
        lines.append(self.report("4. WebSocket transport (round-trip)", self.ws_transport_ms))
        lines.append(self.report("── BACKEND TOTAL (sensor → JSON sent)", self.backend_total_ms))
        lines.append(self.report("── FULL PIPELINE (sensor → client recv)", self.full_pipeline_ms))
        lines.append("═" * 76)
        if self.full_pipeline_ms:
            backend_med = statistics.median(self.backend_total_ms)
            full_med = statistics.median(self.full_pipeline_ms)
            render_ms = 16.7  # 1 frame at 60fps
            total = full_med + render_ms
            stream_period = 1000 / STREAM_HZ
            lines.append(f"  Frontend render (3D scene rebuild):     ~1 frame at 60fps ≈ {render_ms:.1f} ms")
            lines.append(f"  Full pipeline (sensor → pixels):        ~{total:.1f} ms median")
            lines.append(f"  Stream rate:                           {STREAM_HZ} Hz ({stream_period:.0f} ms period)")
            lines.append(f"  Backend processing (sensor → JSON):     {backend_med:.2f} ms median")
            lines.append(f"  WebSocket transport (localhost):        {statistics.median(self.ws_transport_ms):.2f} ms median")
            lines.append("")
            if backend_med < stream_period:
                lines.append(f"  ✓  Backend ({backend_med:.1f} ms) fits within {stream_period:.0f} ms stream period")
            else:
                lines.append(f"  ⚠  Backend ({backend_med:.1f} ms) exceeds {stream_period:.0f} ms stream period")
            if full_med < stream_period:
                lines.append(f"  ✓  Full pipeline ({full_med:.1f} ms) fits within {stream_period:.0f} ms stream period")
            else:
                lines.append(f"  ⚠  Full pipeline ({full_med:.1f} ms) exceeds {stream_period:.0f} ms stream period")
            lines.append("")
            # breakdown by percentage
            if full_med > 0:
                lines.append("  Time budget breakdown:")
                pct_sensor = statistics.median(self.sensor_ms) / full_med * 100
                pct_payload = statistics.median(self.payload_ms) / full_med * 100
                pct_json = statistics.median(self.json_ms) / full_med * 100
                pct_ws = statistics.median(self.ws_transport_ms) / full_med * 100
                lines.append(f"    sensor ray-cast:   {pct_sensor:5.1f}%")
                lines.append(f"    to_payload:        {pct_payload:5.1f}%")
                lines.append(f"    json.dumps:        {pct_json:5.1f}%")
                lines.append(f"    WebSocket transport: {pct_ws:5.1f}%")
        lines.append("═" * 76)
        return "\n".join(lines)


# ── test runner ──────────────────────────────────────────────────────────

N_ITERATIONS = 100
ECHO_PORT = 9877


async def run_latency_test() -> LatencyResults:
    results = LatencyResults()
    m = make_map()

    # start an echo server to measure pure WebSocket transport latency
    _, stop_echo = await start_echo_server(ECHO_PORT)
    ws_url = f"ws://127.0.0.1:{ECHO_PORT}"
    print(f"  Echo server on {ws_url}")

    async with websockets.connect(ws_url) as ws:
        for tick in range(N_ITERATIONS):
            pose = rover_pose_at(tick)

            # ── stage 1: sensor reading → mapper ray-cast ───────────
            t0 = time.perf_counter()
            simulate_sensor_sweep(m, pose, tick)
            t1 = time.perf_counter()

            # ── stage 2: to_payload() ──────────────────────────────
            payload = m.to_payload(pose)
            t2 = time.perf_counter()

            # ── stage 3: JSON serialization ────────────────────────
            payload_json = json.dumps(payload)
            t3 = time.perf_counter()

            backend_total = (t3 - t0) * 1000

            # ── stage 4: WebSocket transport (echo round-trip) ─────
            # send to echo server, it sends back immediately
            t_send = time.perf_counter()
            await ws.send(payload_json)
            echo_msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            t_recv = time.perf_counter()
            ws_transport = (t_recv - t_send) * 1000

            # verify the echo matches
            assert echo_msg == payload_json, "echo mismatch"

            full_pipeline = (t_recv - t0) * 1000

            results.add(
                (t1 - t0) * 1000,
                (t2 - t1) * 1000,
                (t3 - t2) * 1000,
                ws_transport,
                backend_total,
                full_pipeline,
            )

            if tick % 20 == 0:
                print(f"  tick {tick:3d}/{N_ITERATIONS}  "
                      f"ray-cast {(t1-t0)*1e3:6.2f} ms  "
                      f"payload {(t2-t1)*1e3:6.2f} ms  "
                      f"json {(t3-t2)*1e3:6.2f} ms  "
                      f"ws {ws_transport:6.2f} ms  "
                      f"total {full_pipeline:6.2f} ms")

    await stop_echo()
    return results


def run_encoding_comparison(n: int = 200) -> None:
    """Compare JSON serialization: legacy float array vs base64 uint8."""
    import base64

    print("\n" + "═" * 76)
    print("  ENCODING COMPARISON: legacy float array vs base64 uint8")
    print("═" * 76)

    m = make_map()
    # fill the grid with some sensor data so it's not all 0.5
    for tick in range(50):
        simulate_sensor_sweep(m, rover_pose_at(tick), tick)
    pose = rover_pose_at(50)
    payload = m.to_payload(pose)

    prob = 1.0 / (1.0 + np.exp(-m.grid))
    legacy_grid = prob.flatten().tolist()
    legacy_payload = {**payload, "grid": legacy_grid, "grid_encoding": None}

    # ── legacy: float array ──────────────────────────────────────────
    legacy_times: list[float] = []
    legacy_sizes: list[int] = []
    for _ in range(n):
        t0 = time.perf_counter()
        legacy_json = json.dumps(legacy_payload)
        t1 = time.perf_counter()
        legacy_times.append((t1 - t0) * 1000)
        legacy_sizes.append(len(legacy_json))

    # ── new: base64 uint8 ────────────────────────────────────────────
    new_times: list[float] = []
    new_sizes: list[int] = []
    for _ in range(n):
        t0 = time.perf_counter()
        new_json = json.dumps(payload)  # payload already has base64 grid
        t1 = time.perf_counter()
        new_times.append((t1 - t0) * 1000)
        new_sizes.append(len(new_json))

    leg_med = statistics.median(legacy_times)
    new_med = statistics.median(new_times)
    leg_size = statistics.median(legacy_sizes)
    new_size = statistics.median(new_sizes)

    print(f"  {'Metric':30s}  {'Legacy (float[])':>18s}  {'Base64 uint8':>18s}  {'Speedup':>8s}")
    print(f"  {'─'*30}  {'─'*18}  {'─'*18}  {'─'*8}")
    print(f"  {'json.dumps() median':30s}  {leg_med:15.2f} ms  {new_med:15.2f} ms  {leg_med/new_med:6.1f}x")
    print(f"  {'payload size':30s}  {leg_size:15,} B  {new_size:15,} B  {leg_size/new_size:6.1f}x")
    print(f"  {'grid field size':30s}  {len(json.dumps(legacy_grid)):15,} B  {len(payload['grid']):15,} B  {len(json.dumps(legacy_grid))/len(payload['grid']):6.1f}x")
    print("═" * 76)
    print(f"  json.dumps speedup: {leg_med/new_med:.1f}x  ({leg_med:.2f} → {new_med:.2f} ms)")
    print(f"  payload size reduction: {leg_size/new_size:.1f}x  ({leg_size:,} → {new_size:,} bytes)")
    print("═" * 76)


def test_map_latency():
    """Pytest entry point — runs the latency test and prints results."""
    print("\n  Running end-to-end map latency test (100 iterations)...")
    print("  Simulating: ultrasonic + depth + audio + heat + hazards + annotations")
    results = asyncio.run(run_latency_test())
    print(results.summary())
    # assert backend processing is fast
    assert statistics.median(results.sensor_ms) < 50, "Sensor ray-cast too slow"
    assert statistics.median(results.payload_ms) < 100, "to_payload too slow"
    assert statistics.median(results.json_ms) < 50, "json.dumps too slow"
    assert statistics.median(results.ws_transport_ms) < 100, "WebSocket transport too slow"


if __name__ == "__main__":
    run_encoding_comparison()
    print("\n  Running end-to-end map latency test (100 iterations)...")
    print("  Simulating: ultrasonic + depth + audio + heat + hazards + annotations")
    results = asyncio.run(run_latency_test())
    print(results.summary())
