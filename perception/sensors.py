"""Environmental sensors: temperature, microphone (distress/hazard detection), and IMU/gyro.

Real hardware wiring with graceful fallback to safe defaults when sensors
aren't connected. The brain can query these tools without crashing on any
machine.

Hardware:
- Temperature: DS18B20 on 1-Wire (most reliable on Pi) or DHT22 on GPIO.
- Audio: USB webcam mic (same device used for STT via the laptop pipeline).
- Gyro/IMU: MPU6050 on I2C (bus 1, address 0x68).
"""

import glob
import logging
import math
import os
import random
import threading

logger = logging.getLogger(__name__)

WARM_THRESHOLD_C = 42.0
OVERHEAT_THRESHOLD_C = 55.0
AMBIENT_TEMP_C = 22.0
AMBIENT_DB = 32.0

DS18B20_PATH = os.environ.get("DS18B20_PATH", "/sys/bus/w1/devices/28-*/w1_slave")
DHT22_PIN = int(os.environ.get("DHT22_PIN", "4"))
MPU6050_BUS = int(os.environ.get("MPU6050_BUS", "1"))
MPU6050_ADDR = int(os.environ.get("MPU6050_ADDR", "0x68"), 0)

_temp_lock = threading.Lock()
_temp_tried = False
_temp_sensor = None

_imu_lock = threading.Lock()
_imu_tried = False
_imu_bus = None


def _init_temp_sensor():
    """Try DS18B20 first, then DHT22, then give up."""
    global _temp_tried, _temp_sensor
    with _temp_lock:
        if _temp_tried:
            return _temp_sensor
        _temp_tried = True
        try:
            paths = glob.glob(DS18B20_PATH)
            if paths:
                with open(paths[0]) as f:
                    content = f.read()
                if "t=" in content:
                    _temp_sensor = ("ds18b20", paths[0])
                    logger.info("DS18B20 temperature sensor found at %s", paths[0])
                    return _temp_sensor
        except Exception:
            pass
        try:
            import board
            import adafruit_dht
            sensor = adafruit_dht.DHT22(getattr(board, f"D{DHT22_PIN}"))
            _temp_sensor = ("dht22", sensor)
            logger.info("DHT22 temperature sensor found on pin %d", DHT22_PIN)
            return _temp_sensor
        except Exception:
            pass
        logger.info("No temperature sensor found — using ambient stub")
        return None


def _init_imu():
    """Try MPU6050 via I2C."""
    global _imu_tried, _imu_bus
    with _imu_lock:
        if _imu_tried:
            return _imu_bus
        _imu_tried = True
        try:
            from smbus2 import SMBus
            _imu_bus = SMBus(MPU6050_BUS)
            _imu_bus.write_byte_data(MPU6050_ADDR, 0x6B, 0x00)
            logger.info("MPU6050 IMU initialized on I2C bus %d addr 0x%02x", MPU6050_BUS, MPU6050_ADDR)
            return _imu_bus
        except Exception:
            logger.info("MPU6050 IMU unavailable — using stub")
            return None


def _read_word_2c(bus, reg):
    """Read a 16-bit signed value from two consecutive registers."""
    high = bus.read_byte_data(MPU6050_ADDR, reg)
    low = bus.read_byte_data(MPU6050_ADDR, reg + 1)
    val = (high << 8) + low
    if val >= 0x8000:
        val -= 0x10000
    return val


def read_temperature() -> dict:
    """Returns {celsius: float, status: 'ok'|'warm'|'overheat'}."""
    sensor = _init_temp_sensor()
    if sensor is not None:
        kind, dev = sensor
        try:
            if kind == "ds18b20":
                with open(dev) as f:
                    content = f.read()
                if "t=" in content:
                    temp_str = content.split("t=")[-1].strip()
                    temp = float(temp_str) / 1000.0
                    status = "overheat" if temp >= OVERHEAT_THRESHOLD_C else "warm" if temp >= WARM_THRESHOLD_C else "ok"
                    return {"celsius": round(temp, 1), "status": status}
            elif kind == "dht22":
                temp = dev.temperature
                if temp is not None:
                    status = "overheat" if temp >= OVERHEAT_THRESHOLD_C else "warm" if temp >= WARM_THRESHOLD_C else "ok"
                    return {"celsius": round(temp, 1), "status": status}
        except Exception:
            logger.warning("temperature read failed, using stub", exc_info=True)

    temp = AMBIENT_TEMP_C + random.uniform(-0.5, 0.5)
    status = "overheat" if temp >= OVERHEAT_THRESHOLD_C else "warm" if temp >= WARM_THRESHOLD_C else "ok"
    return {"celsius": round(temp, 1), "status": status}


def read_audio() -> dict:
    """Returns {db: float, event: dict|None}.

    event is None when nothing is detected, or:
        {kind: 'distress'|'sound'|'voice', label: str, text: str, bearing_deg: float}

    Ambient audio classification is deferred — the USB webcam mic is already
    used for STT via the laptop pipeline. This stub returns ambient noise
    levels without event detection until a classifier is wired.
    """
    return {"db": AMBIENT_DB + random.uniform(-2, 2), "event": None}


def read_gyro() -> dict:
    """Returns {pitch_deg, roll_deg, yaw_rate_dps, accel_z_g, tipped, bump}.

    yaw_rate_dps is gyro_z angular rate — used by the pose estimator for
    dead-reckoning heading. The MPU6050 has no magnetometer, so yaw drifts
    ~0.25 deg/min.
    """
    bus = _init_imu()
    if bus is not None:
        try:
            accel_x = _read_word_2c(bus, 0x3B) / 16384.0
            accel_y = _read_word_2c(bus, 0x3D) / 16384.0
            accel_z = _read_word_2c(bus, 0x3F) / 16384.0
            gyro_z = _read_word_2c(bus, 0x47) / 131.0

            pitch = math.degrees(math.atan2(-accel_x, math.sqrt(accel_y**2 + accel_z**2)))
            roll = math.degrees(math.atan2(accel_y, math.sqrt(accel_x**2 + accel_z**2)))

            return {
                "pitch_deg": round(pitch, 1),
                "roll_deg": round(roll, 1),
                "yaw_rate_dps": round(gyro_z, 2),
                "accel_z_g": round(accel_z, 2),
                "tipped": abs(pitch) > 45.0 or abs(roll) > 45.0,
                "bump": abs(accel_z - 1.0) > 0.5,
            }
        except Exception:
            logger.warning("IMU read failed, using stub", exc_info=True)

    pitch = random.uniform(-0.5, 0.5)
    roll = random.uniform(-0.5, 0.5)
    yaw_rate = random.uniform(-0.1, 0.1)
    accel_z = 1.0 + random.uniform(-0.01, 0.01)
    return {
        "pitch_deg": round(pitch, 1),
        "roll_deg": round(roll, 1),
        "yaw_rate_dps": round(yaw_rate, 2),
        "accel_z_g": round(accel_z, 2),
        "tipped": abs(pitch) > 45.0,
        "bump": False,
    }
