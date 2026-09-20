import sys

import pytest

from robomaster_smoke_test import _spin, main


class FakeController:
    def __init__(self):
        self.turns = []

    def turn(self, degrees, *, z_speed):
        self.turns.append((degrees, z_speed))


def test_spin_splits_a_full_rotation_into_bounded_turns():
    controller = FakeController()

    _spin(controller, 360, 20)

    assert controller.turns == [(180.0, 20), (180.0, 20)]


def test_spin_requires_explicit_chassis_exercise(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["robomaster_smoke_test.py", "--spin-degrees", "360"])

    with pytest.raises(SystemExit, match="2"):
        main()
