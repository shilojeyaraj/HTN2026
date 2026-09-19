"""HC-SR04 ultrasonic distance sensors on Pi GPIO.

Real distance in meters, 20+ Hz, no Wi-Fi dependency. This is the onboard
reflex source that keeps the robot safe when the laptop depth pipeline is
stale or disconnected (see CAMERA_GAP.md).

Hardware: 1-3 HC-SR04 sensors facing forward (and optionally left/right).
  - TRIG pin: GPIO output, 10us pulse starts measurement
  - ECHO pin: GPIO input, pulse width = round-trip time of flight
  - Distance = (pulse_width_s * 343 m/s) / 2

  WARNING: HC-SR04 ECHO outputs 5V. Pi GPIO is 3.3V. Use a voltage divider
  (1k + 2k resistors) on the ECHO pin, or you'll damage the Pi.

gpiozero's DistanceSensor handles the timing internally and exposes a
.distance property that can be polled at any rate.

Environment variables (all optional, with defaults):
  ULTRASONIC_TRIG_FRONT  — default GPIO 23
  ULTRASONIC_ECHO_FRONT  — default GPIO 24
  ULTRASONIC_TRIG_LEFT   — default GPIO 5
  ULTRASONIC_ECHO_LEFT   — default GPIO 6
  ULTRASONIC_TRIG_RIGHT  — default GPIO 12
  ULTRASONIC_ECHO_RIGHT  — default GPIO 16

On Mac (no GPIO): is_available() returns False, read_ultrasonic() returns
empty readings, read_ultrasonic_detections() returns empty list.
"""

import logging
import os
import threading

from brain.state import Detection

logger = logging.getLogger(__name__)

SPEED_OF_SOUND = 343.0
MAX_RANGE_M = 4.0
MIN_RANGE_M = 0.02

SENSOR_CONFIG = {
    "front": {
        "trig": int(os.environ.get("ULTRASONIC_TRIG_FRONT", "23")),
        "echo": int(os.environ.get("ULTRASONIC_ECHO_FRONT", "24")),
        "bearing": 0.0,
    },
    "left": {
        "trig": int(os.environ.get("ULTRASONIC_TRIG_LEFT", "5")),
        "echo": int(os.environ.get("ULTRASONIC_ECHO_LEFT", "6")),
        "bearing": -30.0,
    },
    "right": {
        "trig": int(os.environ.get("ULTRASONIC_TRIG_RIGHT", "12")),
        "echo": int(os.environ.get("ULTRASONIC_ECHO_RIGHT", "16")),
        "bearing": 30.0,
    },
}

_sensors: dict = {}
_sensors_lock = threading.Lock()
_tried_init = False


def _init_sensors() -> dict:
    """Lazily create and cache gpiozero DistanceSensor objects."""
    global _tried_init
    with _sensors_lock:
        if _tried_init:
            return _sensors
        _tried_init = True
        try:
            from gpiozero import DistanceSensor
        except ImportError:
            logger.warning("gpiozero not available — ultrasonic sensors disabled")
            return _sensors
        for name, cfg in SENSOR_CONFIG.items():
            try:
                _sensors[name] = DistanceSensor(
                    echo=cfg["echo"],
                    trigger=cfg["trig"],
                    max_distance=MAX_RANGE_M,
                )
                logger.info("ultrasonic %s sensor initialized on GPIO %d/%d",
                            name, cfg["trig"], cfg["echo"])
            except Exception:
                logger.warning("failed to init %s ultrasonic sensor (GPIO %d/%d)",
                               name, cfg["trig"], cfg["echo"], exc_info=True)
        return _sensors


def is_available() -> bool:
    """True if at least one ultrasonic sensor is connected."""
    return bool(_init_sensors())


def read_ultrasonic() -> dict:
    """Read all connected sensors. Returns a dict for the brain:

    {"front_m": 0.45, "left_m": null, "right_m": 2.1, "available": true}

    null means that sensor isn't connected or timed out.
    """
    sensors = _init_sensors()
    if not sensors:
        return {"front_m": None, "left_m": None, "right_m": None, "available": False}

    result = {"available": True}
    for name in ("front", "left", "right"):
        sensor = sensors.get(name)
        if sensor is None:
            result[f"{name}_m"] = None
            continue
        try:
            dist = sensor.distance
            result[f"{name}_m"] = round(dist, 3) if MIN_RANGE_M <= dist <= MAX_RANGE_M else None
        except Exception:
            result[f"{name}_m"] = None
    return result


def read_ultrasonic_detections() -> list[Detection]:
    """Read sensors and return Detection objects for the reflex loop.

    Only includes sensors that returned a valid reading within range.
    Empty list means either no sensors connected or no obstacles detected.
    """
    sensors = _init_sensors()
    if not sensors:
        return []

    detections = []
    for name, cfg in SENSOR_CONFIG.items():
        sensor = sensors.get(name)
        if sensor is None:
            continue
        try:
            dist = sensor.distance
            if MIN_RANGE_M <= dist <= MAX_RANGE_M:
                detections.append(Detection(
                    label="obstacle",
                    bbox=(0.0, 0.0, 0.0, 0.0),
                    distance_m=round(dist, 3),
                    bearing_deg=cfg["bearing"],
                ))
        except Exception:
            pass
    return detections
