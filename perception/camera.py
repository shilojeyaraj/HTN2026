"""Camera bridge: USB webcam frames + monocular depth from laptop over TCP.

The Pi captures USB webcam video via FFmpeg (pi/client.py) and streams it to
the laptop depth server (laptop/server.py). Depth results are pushed into
the shared DepthBuffer by pi/client.py, and this module reads from there.

The laptop runs Depth-Anything-V2-Small and returns:
  - relative_proximity: {left, center, right} scores (0-1, higher = nearer)
  - preferred_direction: most open path
  - advisory_only: true (monocular depth is relative, not absolute meters)

We convert proximity to pseudo-detections:
  - distance_m = 1.0 - proximity_score  (monotonic, not true meters)
  - bearing_deg: left=-30, center=0, right=+30
  - label: "obstacle"

Ultrasonic (HC-SR04) is the onboard source that keeps the robot safe when
Wi-Fi depth is stale. When both are available, we merge. When neither is
available, we fail closed (return a "blocked ahead" detection) so the reflex
loop stops the robot.
"""

import logging

from brain.state import Detection
from perception import ultrasonic
from perception.depth_buffer import get_buffer

logger = logging.getLogger(__name__)

REGION_BEARINGS = {"left": -30.0, "center": 0.0, "right": 30.0}
OBSTACLE_THRESHOLD = 0.5
DEPTH_STALENESS_S = 2.0


def _proximity_to_detections(depth_result: dict) -> list[Detection]:
    """Convert relative proximity scores to pseudo-Detection objects."""
    proximity = depth_result.get("relative_proximity")
    if not proximity or depth_result.get("status") != "ok":
        return []

    detections = []
    for region, bearing in REGION_BEARINGS.items():
        score = proximity.get(region)
        if score is not None and score > OBSTACLE_THRESHOLD:
            distance_m = round(1.0 - score, 2)
            detections.append(Detection(
                label="obstacle",
                bbox=(0.0, 0.0, 0.0, 0.0),
                distance_m=distance_m,
                bearing_deg=bearing,
            ))
    return detections


def get_latest_frame() -> tuple[bytes, list[Detection]]:
    """Return the latest JPEG frame and detections for the brain's vision step."""
    buf = get_buffer()
    return buf.get_frame(), get_latest_detections()


def get_latest_detections() -> list[Detection]:
    """Return obstacle detections from ultrasonic + depth. Fail closed when
    both are unavailable.

    Ultrasonic (HC-SR04) is the primary onboard source — real distance in
    meters, no Wi-Fi dependency. Depth from the laptop is secondary. When both
    are available, we merge. When neither is available, return a "blocked
    ahead" detection so the reflex loop stops the robot. A robot that halts
    when it can't see is safe; one that keeps driving blind is not.
    """
    ultra = ultrasonic.read_ultrasonic_detections()
    depth_result = get_buffer().get_depth_if_fresh(DEPTH_STALENESS_S)
    depth = _proximity_to_detections(depth_result) if depth_result else None

    if ultrasonic.is_available():
        if depth is not None:
            return ultra + depth
        return ultra
    elif depth is not None:
        return depth
    else:
        return [Detection(
            label="obstacle",
            bbox=(0.0, 0.0, 0.0, 0.0),
            distance_m=0.0,
            bearing_deg=0.0,
        )]
