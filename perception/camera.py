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

When depth is unavailable (Wi-Fi down, laptop server not running), we fail
closed (return a "blocked ahead" detection) so the reflex loop stops the robot.
"""

import logging

from brain.state import Detection
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
    """Return obstacle detections from monocular depth. Fail closed when
    depth is unavailable.

    Depth from the laptop (Depth-Anything-V2-Small) is the primary source.
    When depth is stale or unavailable, return a "blocked ahead" detection
    so the reflex loop stops the robot. A robot that halts when it can't
    see is safe; one that keeps driving blind is not.
    """
    depth_result = get_buffer().get_depth_if_fresh(DEPTH_STALENESS_S)
    depth = _proximity_to_detections(depth_result) if depth_result else None

    if depth is not None:
        return depth
    return [Detection(
        label="obstacle",
        bbox=(0.0, 0.0, 0.0, 0.0),
        distance_m=0.0,
        bearing_deg=0.0,
    )]
