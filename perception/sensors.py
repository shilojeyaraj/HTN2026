"""Environmental sensors: temperature, microphone (distress/hazard detection), and IMU/gyro.

Real hardware wiring is deferred (CLAUDE.md section 8). Stubs return safe defaults so the
brain can query these tools without crashing when sensors aren't connected yet.

Hardware plan:
- Temperature: DHT22 or DS18B20 on a GPIO pin, or OAK-D onboard IMU temp.
- Audio: USB webcam mic (same device used for push-to-talk STT).
- Gyro/IMU: MPU6050 on I2C, or OAK-D S2's onboard IMU.
"""

import random

WARM_THRESHOLD_C = 42.0
OVERHEAT_THRESHOLD_C = 55.0
AMBIENT_TEMP_C = 22.0
AMBIENT_DB = 32.0


def read_temperature() -> dict:
    """Returns {celsius: float, status: 'ok'|'warm'|'overheat'}."""
    # TODO: replace with real DHT22/DS18B20 reading
    temp = AMBIENT_TEMP_C + random.uniform(-0.5, 0.5)
    status = "overheat" if temp >= OVERHEAT_THRESHOLD_C else "warm" if temp >= WARM_THRESHOLD_C else "ok"
    return {"celsius": round(temp, 1), "status": status}


def read_audio() -> dict:
    """Returns {db: float, event: dict|None}.

    event is None when nothing is detected, or:
        {kind: 'distress'|'sound'|'voice', label: str, text: str, bearing_deg: float}
    """
    # TODO: replace with real mic capture + classification
    # The push-to-talk loop already uses the mic for STT; this is for ambient
    # listening (screams, hazard noise) between button presses.
    return {"db": AMBIENT_DB + random.uniform(-2, 2), "event": None}


def read_gyro() -> dict:
    """Returns {pitch_deg, roll_deg, yaw_rate_dps, accel_z_g, tipped, bump}.

    yaw_rate_dps is gyro_z angular rate — used by the pose estimator for dead-reckoning
    heading. The MPU6050 has no magnetometer, so yaw drifts ~0.25 deg/min.
    """
    # TODO: replace with real MPU6050/OAK-D IMU reading
    pitch = random.uniform(-0.5, 0.5)
    roll = random.uniform(-0.5, 0.5)
    yaw_rate = random.uniform(-0.1, 0.1)  # near-zero when stationary
    accel_z = 1.0 + random.uniform(-0.01, 0.01)
    return {
        "pitch_deg": round(pitch, 1),
        "roll_deg": round(roll, 1),
        "yaw_rate_dps": round(yaw_rate, 2),
        "accel_z_g": round(accel_z, 2),
        "tipped": abs(pitch) > 45.0,
        "bump": False,
    }
