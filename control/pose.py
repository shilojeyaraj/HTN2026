"""Dead-reckoning pose estimator: integrates IMU yaw rate + commanded linear velocity
to track (x, y, heading) without wheel encoders. Runs in the reflex loop at 30 Hz.

Drift: MPU6050 yaw drifts ~0.25 deg/min after calibration — negligible for a 5-minute
demo map. Position accuracy depends on how well commanded velocity matches actual
speed (~10-20% error expected with open-loop PWM).
"""

import math
import time

GYRO_CALIBRATION_SAMPLES = 500


class PoseEstimator:
    def __init__(self):
        self.x = 0.0
        self.y = 0.0
        self.heading_rad = 0.0
        self._gyro_z_bias_dps = 0.0
        self._last_time = None

    def calibrate(self, read_gyro_z_dps) -> None:
        """Average gyro_z while stationary to find the bias offset."""
        readings = [read_gyro_z_dps() for _ in range(GYRO_CALIBRATION_SAMPLES)]
        self._gyro_z_bias_dps = sum(readings) / len(readings)

    def update(self, gyro_z_dps: float, linear_velocity: float, dt: float | None = None) -> tuple[float, float, float]:
        """Dead-reckon one step. Returns (x, y, heading_deg)."""
        if dt is None:
            now = time.monotonic()
            dt = now - self._last_time if self._last_time else 0.0
            self._last_time = now
        else:
            self._last_time = time.monotonic()

        heading_rate_rad = math.radians(gyro_z_dps - self._gyro_z_bias_dps)
        self.heading_rad += heading_rate_rad * dt
        self.x += linear_velocity * math.cos(self.heading_rad) * dt
        self.y += linear_velocity * math.sin(self.heading_rad) * dt
        return (self.x, self.y, math.degrees(self.heading_rad))

    @property
    def pose(self) -> tuple[float, float, float]:
        return (self.x, self.y, math.degrees(self.heading_rad))
