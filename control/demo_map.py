"""Demo: drive a simulated rover through a rescue scenario, firing all sensor
types into the occupancy map so you can watch each overlay layer build up on
the frontend with the polished visuals.

Run:
    python control/demo_map.py
Then open the frontend Dashboard — the map populates in realtime with
obstacles, speech markers, heat domes, hazard triangles, and annotations.

Visual layers you should see:
  - Smooth heat-field occupancy grid (cyan=free, amber=occupied)
  - Rover with green glow + sensor cone (semi-transparent cyan)
  - Trail with gradient opacity (fades from old to new)
  - Sound markers with expanding ripple rings (distress=red, voice=blue, speech=purple)
  - Heat domes with glow (warm=amber, overheat=red)
  - Hazard triangles with red glow
  - Annotation pins with text labels (Gemini scene descriptions)
  - Subtle radar grid lines
"""

import math
import time
import threading
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from control.mapper import OccupancyMap
from control.map_server import MapServer
from control.pose import PoseEstimator


def drive_path(pose_est: PoseEstimator, mapper: OccupancyMap):
    """Simulate a rover driving a rescue search pattern, feeding sensor readings."""

    steps = [
        # (linear_vel, angular_vel_deg, duration_s, sensors_to_fire)
        (0.3, 0,   3.0, ["ultrasonic_ahead"]),
        (0.0, 45,  1.0, []),
        (0.3, 0,   2.0, ["ultrasonic_right", "depth_ahead"]),
        (0.0, -30, 1.0, ["transcript_help_partial"]),
        (0.2, 0,   2.0, ["sound_distress", "heat_warm"]),
        (0.0, 60,  1.0, ["hazard_bump"]),
        (0.15, 0,  3.0, ["ultrasonic_left", "annotation_person"]),
        (0.0, -90, 1.5, ["transcript_help_final"]),
        (0.25, 0,   3.0, ["ultrasonic_ahead", "depth_right", "sound_voice"]),
        (0.0, 45,  1.0, ["heat_overheat"]),
        (0.2, 0,   2.0, ["annotation_rubble", "ultrasonic_left"]),
        (0.0, -45, 1.0, ["transcript_forward"]),
        (0.2, 0,   2.5, ["ultrasonic_ahead", "depth_ahead", "sound_voice"]),
        (0.0, 30,  1.0, ["annotation_survivor"]),
        (0.15, 0,  2.0, ["ultrasonic_right", "transcript_stop"]),
    ]

    dt = 0.1
    for lin_vel, ang_vel, duration, sensors in steps:
        n_ticks = int(duration / dt)
        for i in range(n_ticks):
            pose_est.update(gyro_z_dps=ang_vel, linear_velocity=lin_vel, dt=dt)
            pose = pose_est.pose
            mapper.add_trail(pose)

            for sensor in sensors:
                _fire_sensor(mapper, pose, sensor, tick=i, total=n_ticks)

            time.sleep(dt)


def _fire_sensor(mapper, pose, sensor, tick, total):
    x, y, heading = pose

    if sensor == "ultrasonic_ahead":
        dist = 1.2 + 0.15 * math.sin(tick * 0.3)
        mapper.add_ultrasonic(pose, bearing_deg=0, distance_m=dist)
        mapper.add_ultrasonic(pose, bearing_deg=-15, distance_m=dist + 0.3)
        mapper.add_ultrasonic(pose, bearing_deg=15, distance_m=dist + 0.3)

    elif sensor == "ultrasonic_right":
        mapper.add_ultrasonic(pose, bearing_deg=45, distance_m=0.8)
        mapper.add_ultrasonic(pose, bearing_deg=60, distance_m=1.0)

    elif sensor == "ultrasonic_left":
        mapper.add_ultrasonic(pose, bearing_deg=-45, distance_m=1.5)
        mapper.add_ultrasonic(pose, bearing_deg=-30, distance_m=1.2)

    elif sensor == "depth_ahead":
        mapper.add_depth(pose, bearing_deg=0, proximity=0.7)
        mapper.add_depth(pose, bearing_deg=10, proximity=0.5)

    elif sensor == "depth_right":
        mapper.add_depth(pose, bearing_deg=30, proximity=0.6)

    elif sensor == "sound_distress":
        if tick == 0:
            mapper.add_sound(pose, kind="distress", label="DISTRESS CALL", db=85)

    elif sensor == "sound_voice":
        if tick == 0:
            mapper.add_sound(pose, kind="voice", label="voice detected", db=65)

    elif sensor == "transcript_help_partial":
        if tick == 0:
            mapper.add_transcript(pose, "help", final=False)

    elif sensor == "transcript_help_final":
        if tick == 0:
            mapper.add_transcript(pose, "help me, I'm over here", final=True)

    elif sensor == "transcript_forward":
        if tick == 0:
            mapper.add_transcript(pose, "forward two meters", final=True)

    elif sensor == "transcript_stop":
        if tick == 0:
            mapper.add_transcript(pose, "stop", final=True)

    elif sensor == "heat_warm":
        if tick == 0:
            mapper.add_heat(pose, celsius=38.5, status="warm")

    elif sensor == "heat_overheat":
        if tick == 0:
            mapper.add_heat(pose, celsius=72.0, status="overheat")

    elif sensor == "hazard_bump":
        if tick == 0:
            mapper.add_hazard(pose, hazard_type="bump")

    elif sensor == "annotation_person":
        if tick == 0:
            mapper.add_annotation(pose, "person lying on ground", source="gemini")

    elif sensor == "annotation_rubble":
        if tick == 0:
            mapper.add_annotation(pose, "rubble pile blocking path", source="gemini")

    elif sensor == "annotation_survivor":
        if tick == 0:
            mapper.add_annotation(pose, "survivor located — stable", source="gemini")


def main():
    pose_est = PoseEstimator()
    mapper = OccupancyMap(size_m=8.0, resolution_m=0.1)

    server = MapServer(mapper, lambda: pose_est.pose)
    threading.Thread(target=server.run_forever, daemon=True).start()
    print("Map server streaming on ws://0.0.0.0:8766 — open the frontend Dashboard")
    print("Simulating rescue scenario with all sensor types...")
    print("  ultrasonic (amber obstacles)")
    print("  depth camera (lower-confidence obstacles)")
    print("  sound markers (distress=red, voice=blue, speech=purple)")
    print("  heat domes (warm=amber, overheat=red)")
    print("  hazard triangles (red glow)")
    print("  annotations (Gemini scene descriptions)")
    print("  rover sensor cone (semi-transparent cyan)")
    print("  trail with gradient opacity (green)")
    print()

    drive_path(pose_est, mapper)

    print(f"\nDone. Rover final pose: {pose_est.pose}")
    print(f"  {len(mapper.sound_sources)} sound/speech markers, "
          f"{len(mapper.heat_points)} heat points, {len(mapper.hazards)} hazards, "
          f"{len(mapper.annotations)} annotations, {len(mapper.trail)} trail points")
    print("Map server alive — press Ctrl+C to stop. Open the frontend to view.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
