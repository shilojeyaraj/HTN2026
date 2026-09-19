"""GPS module for the Pi. Reads NMEA sentences from a serial UART device.

Hardware: USB GPS receiver (e.g. GlobalSat BU-353-S4) or a UART GPS module
on GPIO 14/15 (TX/RX). Most USB GPS modules appear as /dev/ttyUSB0 or
/dev/ttyAMA0.

Env vars:
    GPS_DEVICE — serial device path (default: /dev/ttyUSB0)
    GPS_BAUD   — baud rate (default: 4800)

On Mac (no serial): is_available() returns False, read_gps() returns
a safe default with status "unavailable".
"""

import logging
import os
import threading

logger = logging.getLogger(__name__)

GPS_DEVICE = os.environ.get("GPS_DEVICE", "/dev/ttyUSB0")
GPS_BAUD = int(os.environ.get("GPS_BAUD", "4800"))

_serial = None
_lock = threading.Lock()
_tried_init = False


def _init_serial():
    global _serial, _tried_init
    with _lock:
        if _tried_init:
            return _serial
        _tried_init = True
        try:
            import serial
            _serial = serial.Serial(GPS_DEVICE, GPS_BAUD, timeout=1.0)
            logger.info("GPS initialized on %s @ %d baud", GPS_DEVICE, GPS_BAUD)
        except Exception:
            logger.warning("GPS unavailable on %s — using dead-reckoning only", GPS_DEVICE)
        return _serial


def is_available() -> bool:
    return _init_serial() is not None


def read_gps() -> dict:
    """Returns {lat, lon, speed_knots, heading_deg, status}.

    status is 'ok' when a fix is available, 'no_fix' when the GPS is connected
    but has no satellite fix, or 'unavailable' when the GPS device is not
    connected.
    """
    ser = _init_serial()
    if ser is None:
        return {"lat": None, "lon": None, "speed_knots": None,
                "heading_deg": None, "status": "unavailable"}

    try:
        for _ in range(10):
            line = ser.readline().decode("ascii", errors="ignore").strip()
            if line.startswith("$GPRMC") or line.startswith("$GNRMC"):
                parts = line.split(",")
                if parts[2] == "A":
                    lat = _parse_lat(parts[3], parts[4])
                    lon = _parse_lon(parts[5], parts[6])
                    speed = float(parts[7]) if parts[7] else None
                    heading = float(parts[8]) if parts[8] else None
                    return {"lat": lat, "lon": lon, "speed_knots": speed,
                            "heading_deg": heading, "status": "ok"}
                return {"lat": None, "lon": None, "speed_knots": None,
                        "heading_deg": None, "status": "no_fix"}
    except Exception:
        logger.warning("GPS read failed", exc_info=True)

    return {"lat": None, "lon": None, "speed_knots": None,
            "heading_deg": None, "status": "no_fix"}


def _parse_lat(value, direction):
    if not value:
        return None
    deg = float(value[:2])
    minutes = float(value[2:])
    lat = deg + minutes / 60
    return -lat if direction == "S" else lat


def _parse_lon(value, direction):
    if not value:
        return None
    deg = float(value[:3])
    minutes = float(value[3:])
    lon = deg + minutes / 60
    return -lon if direction == "W" else lon
