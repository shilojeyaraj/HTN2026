"""Bench control for an L298N dual H-bridge and two quadrature encoders.

Edit BENCH_CONFIG before running on the Pi. GPIO numbers are BCM numbers.
The L298N's ENA and ENB jumpers must be removed so the Pi can PWM them.

Run one bounded movement:
    python3 -m control.l298n forward 100
    python3 -m control.l298n clockwise 90
    python3 -m control.l298n counterclockwise 90
"""

from __future__ import annotations

import argparse
import math
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class L298NConfig:
    # L298N control pins. Fill these with BCM GPIO numbers.
    left_enable: int | None = None  # ENA
    left_in1: int | None = None     # IN1
    left_in2: int | None = None     # IN2
    right_enable: int | None = None  # ENB
    right_in1: int | None = None     # IN3
    right_in2: int | None = None     # IN4

    # Each encoder needs its A and B signals wired to the Pi, plus common GND.
    left_encoder_a: int | None = None
    left_encoder_b: int | None = None
    right_encoder_a: int | None = None
    right_encoder_b: int | None = None

    # Flip either after the first bench test if semantic "forward" is backwards.
    left_reversed: bool = False
    right_reversed: bool = False

    forward_duty: float = 0.45
    turn_duty: float = 0.65
    pwm_hz: int = 1_000
    poll_s: float = 0.005
    timeout_s: float = 10.0

    # Measure this after wheels are mounted. It is encoder units per degree for
    # an in-place turn, so wheel diameter, track width, traction, and gearing all matter.
    turn_units_per_degree: float | None = None

    def validate(self) -> None:
        missing = [
            name for name in (
                "left_enable", "left_in1", "left_in2", "right_enable", "right_in1", "right_in2",
                "left_encoder_a", "left_encoder_b", "right_encoder_a", "right_encoder_b",
            )
            if getattr(self, name) is None
        ]
        if missing:
            raise ValueError(f"Set BCM GPIO numbers in BENCH_CONFIG: {', '.join(missing)}")
        if not all(0 < duty <= 1 for duty in (self.forward_duty, self.turn_duty)):
            raise ValueError("forward_duty and turn_duty must be in (0, 1]")
        if self.pwm_hz <= 0 or self.poll_s <= 0 or self.timeout_s <= 0:
            raise ValueError("pwm_hz, poll_s, and timeout_s must be positive")


# Fill every None before using the command-line tool. No GPIO is touched on import.
BENCH_CONFIG = L298NConfig()


class _Channel:
    """One L298N bridge: PWM on enable, direction on its two inputs."""

    def __init__(self, enable, in1, in2, reversed_: bool = False):
        self.enable = enable
        self.in1 = in1
        self.in2 = in2
        self.reversed = reversed_
        self.stop()

    def set_speed(self, speed: float) -> None:
        if not -1 <= speed <= 1:
            raise ValueError("motor speed must be between -1 and 1")
        if self.reversed:
            speed = -speed

        # Disable before changing direction so a reverse never briefly drives both ways.
        self.enable.value = 0
        if speed > 0:
            self.in1.on()
            self.in2.off()
        elif speed < 0:
            self.in1.off()
            self.in2.on()
        else:
            self.in1.off()
            self.in2.off()
        self.enable.value = abs(speed)

    def stop(self) -> None:
        self.enable.value = 0
        self.in1.off()
        self.in2.off()

    def close(self) -> None:
        self.stop()
        for device in (self.enable, self.in1, self.in2):
            close = getattr(device, "close", None)
            if close:
                close()


class L298NDrive:
    """Two L298N channels with encoder-bounded bench motions."""

    def __init__(self, config: L298NConfig, left: _Channel, right: _Channel,
                 left_encoder, right_encoder, *, sleep=time.sleep, monotonic=time.monotonic):
        self.config = config
        self.left = left
        self.right = right
        self.left_encoder = left_encoder
        self.right_encoder = right_encoder
        self._sleep = sleep
        self._monotonic = monotonic

    @classmethod
    def from_gpio(cls, config: L298NConfig) -> "L298NDrive":
        """Create the real Pi GPIO devices. Kept separate so tests need no Pi."""
        config.validate()
        from gpiozero import DigitalOutputDevice, PWMOutputDevice, RotaryEncoder

        left = _Channel(
            PWMOutputDevice(config.left_enable, frequency=config.pwm_hz),
            DigitalOutputDevice(config.left_in1),
            DigitalOutputDevice(config.left_in2),
            config.left_reversed,
        )
        right = _Channel(
            PWMOutputDevice(config.right_enable, frequency=config.pwm_hz),
            DigitalOutputDevice(config.right_in1),
            DigitalOutputDevice(config.right_in2),
            config.right_reversed,
        )
        return cls(
            config,
            left,
            right,
            RotaryEncoder(config.left_encoder_a, config.left_encoder_b, max_steps=0),
            RotaryEncoder(config.right_encoder_a, config.right_encoder_b, max_steps=0),
        )

    def _run(self, left_speed: float, right_speed: float, target_units: int, timeout_s: float | None) -> dict:
        if not isinstance(target_units, int) or target_units <= 0:
            raise ValueError("encoder_units must be a positive integer")
        timeout_s = self.config.timeout_s if timeout_s is None else timeout_s
        if not math.isfinite(timeout_s) or timeout_s <= 0:
            raise ValueError("timeout_s must be positive and finite")

        left_start = self.left_encoder.steps
        right_start = self.right_encoder.steps
        left_done = right_done = False
        deadline = self._monotonic() + timeout_s
        self.left.set_speed(left_speed)
        self.right.set_speed(right_speed)
        try:
            while not (left_done and right_done):
                left_units = abs(self.left_encoder.steps - left_start)
                right_units = abs(self.right_encoder.steps - right_start)
                if left_units >= target_units and not left_done:
                    self.left.stop()
                    left_done = True
                if right_units >= target_units and not right_done:
                    self.right.stop()
                    right_done = True
                if left_done and right_done:
                    return {
                        "status": "completed",
                        "target_encoder_units": target_units,
                        "left_encoder_units": left_units,
                        "right_encoder_units": right_units,
                    }
                if self._monotonic() >= deadline:
                    return {
                        "status": "timed_out",
                        "target_encoder_units": target_units,
                        "left_encoder_units": left_units,
                        "right_encoder_units": right_units,
                    }
                self._sleep(self.config.poll_s)
        finally:
            self.stop()

    def forward(self, encoder_units: int, *, timeout_s: float | None = None) -> dict:
        """Run both sides forward until each encoder has advanced encoder_units."""
        return self._run(self.config.forward_duty, self.config.forward_duty, encoder_units, timeout_s)

    def _turn(self, degrees: float, clockwise: bool, timeout_s: float | None) -> dict:
        if not math.isfinite(degrees) or degrees <= 0:
            raise ValueError("degrees must be positive and finite")
        units_per_degree = self.config.turn_units_per_degree
        if units_per_degree is None or units_per_degree <= 0:
            raise ValueError("Set turn_units_per_degree after calibrating an in-place turn")
        target_units = math.ceil(degrees * units_per_degree)

        # Viewed from above: clockwise is left forward and right backward.
        left_speed = self.config.turn_duty if clockwise else -self.config.turn_duty
        right_speed = -self.config.turn_duty if clockwise else self.config.turn_duty
        result = self._run(left_speed, right_speed, target_units, timeout_s)
        result["degrees"] = degrees
        return result

    def turn_clockwise(self, degrees: float, *, timeout_s: float | None = None) -> dict:
        """Turn in place clockwise by a calibrated number of degrees."""
        return self._turn(degrees, clockwise=True, timeout_s=timeout_s)

    def turn_counterclockwise(self, degrees: float, *, timeout_s: float | None = None) -> dict:
        """Turn in place counterclockwise by a calibrated number of degrees."""
        return self._turn(degrees, clockwise=False, timeout_s=timeout_s)

    def stop(self) -> None:
        self.left.stop()
        self.right.stop()

    def close(self) -> None:
        self.left.close()
        self.right.close()
        for encoder in (self.left_encoder, self.right_encoder):
            close = getattr(encoder, "close", None)
            if close:
                close()

    def __enter__(self) -> "L298NDrive":
        return self

    def __exit__(self, *_exc_info) -> None:
        self.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--timeout", type=float, default=None)
    commands = parser.add_subparsers(dest="command", required=True)
    forward = commands.add_parser("forward", help="run both motors by encoder units")
    forward.add_argument("encoder_units", type=int)
    clockwise = commands.add_parser("clockwise", help="turn clockwise in place")
    clockwise.add_argument("degrees", type=float)
    counterclockwise = commands.add_parser("counterclockwise", help="turn counterclockwise in place")
    counterclockwise.add_argument("degrees", type=float)
    args = parser.parse_args()

    with L298NDrive.from_gpio(BENCH_CONFIG) as drive:
        if args.command == "forward":
            result = drive.forward(args.encoder_units, timeout_s=args.timeout)
        elif args.command == "clockwise":
            result = drive.turn_clockwise(args.degrees, timeout_s=args.timeout)
        else:
            result = drive.turn_counterclockwise(args.degrees, timeout_s=args.timeout)
    print(result)
    if result["status"] != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
