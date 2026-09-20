"""Differential-drive motor driver for the Pi.

Converts (linear, angular) velocity commands from the arbiter into left/right
wheel PWM signals via gpiozero. Falls back to a no-op logger when GPIO is
unavailable (development on Mac, no chassis wired yet).

Differential-drive kinematics (CLAUDE.md section 6):
    left  = linear - angular * wheelbase / 2
    right = linear + angular * wheelbase / 2

Hardware: L298N or TB6612 motor driver. Each motor needs a PWM pin (speed)
and two direction pins (IN1/IN2). gpiozero's PWMOutputDevice controls speed;
DigitalOutputDevice controls direction.

Env vars (all optional, with defaults):
    MOTOR_LEFT_PWM    — default GPIO 12
    MOTOR_LEFT_IN1    — default GPIO 5
    MOTOR_LEFT_IN2    — default GPIO 6
    MOTOR_RIGHT_PWM   — default GPIO 13
    MOTOR_RIGHT_IN1   — default GPIO 19
    MOTOR_RIGHT_IN2   — default GPIO 26
    MOTOR_WHEELBASE_M — default 0.18
    MOTOR_MAX_PWM     — default 1.0 (duty cycle fraction, 0-1)
"""

import logging
import os
import threading

logger = logging.getLogger(__name__)

WHEELBASE_M = float(os.environ.get("MOTOR_WHEELBASE_M", "0.18"))
MAX_PWM = float(os.environ.get("MOTOR_MAX_PWM", "1.0"))

LEFT_PWM = int(os.environ.get("MOTOR_LEFT_PWM", "12"))
LEFT_IN1 = int(os.environ.get("MOTOR_LEFT_IN1", "5"))
LEFT_IN2 = int(os.environ.get("MOTOR_LEFT_IN2", "6"))
RIGHT_PWM = int(os.environ.get("MOTOR_RIGHT_PWM", "13"))
RIGHT_IN1 = int(os.environ.get("MOTOR_RIGHT_IN1", "19"))
RIGHT_IN2 = int(os.environ.get("MOTOR_RIGHT_IN2", "26"))


class MotorDriver:
    """Publishes (linear, angular) to real motors via gpiozero PWM.

    When GPIO is unavailable, falls back to a no-op logger so the full stack
    runs on any machine without crashing.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._available = False
        self._left_pwm = None
        self._left_in1 = None
        self._left_in2 = None
        self._right_pwm = None
        self._right_in1 = None
        self._right_in2 = None
        self._init_hardware()

    def _init_hardware(self):
        try:
            from gpiozero import PWMOutputDevice, DigitalOutputDevice
        except ImportError:
            logger.warning("gpiozero not available — motor driver in no-op mode")
            return
        try:
            self._left_pwm = PWMOutputDevice(LEFT_PWM)
            self._left_in1 = DigitalOutputDevice(LEFT_IN1)
            self._left_in2 = DigitalOutputDevice(LEFT_IN2)
            self._right_pwm = PWMOutputDevice(RIGHT_PWM)
            self._right_in1 = DigitalOutputDevice(RIGHT_IN1)
            self._right_in2 = DigitalOutputDevice(RIGHT_IN2)
            self._available = True
            logger.info("Motor driver initialized: L(PWM=%d IN1=%d IN2=%d) R(PWM=%d IN1=%d IN2=%d)",
                        LEFT_PWM, LEFT_IN1, LEFT_IN2, RIGHT_PWM, RIGHT_IN1, RIGHT_IN2)
        except Exception:
            logger.warning("Motor driver init failed — no-op mode", exc_info=True)

    @property
    def available(self) -> bool:
        return self._available

    def publish_cmd_vel(self, linear: float, angular: float) -> None:
        """Convert (linear, angular) to left/right wheel PWM and drive motors."""
        if not self._available:
            logger.debug("motors no-op: linear=%.2f angular=%.2f", linear, angular)
            return

        left = linear - angular * WHEELBASE_M / 2
        right = linear + angular * WHEELBASE_M / 2

        with self._lock:
            self._drive_wheel(self._left_pwm, self._left_in1, self._left_in2, left)
            self._drive_wheel(self._right_pwm, self._right_in1, self._right_in2, right)

    @staticmethod
    def _drive_wheel(pwm, in1, in2, speed: float) -> None:
        clamped = max(-MAX_PWM, min(MAX_PWM, abs(speed)))
        if speed >= 0:
            in1.on()
            in2.off()
        else:
            in1.off()
            in2.on()
        pwm.value = clamped

    def stop(self) -> None:
        if not self._available:
            return
        with self._lock:
            self._left_pwm.value = 0
            self._right_pwm.value = 0
