from robomaster_smoke_test import _spin


class FakeController:
    def __init__(self):
        self.turns = []

    def turn(self, degrees, *, z_speed):
        self.turns.append((degrees, z_speed))


def test_spin_splits_a_full_rotation_into_bounded_turns():
    controller = FakeController()

    _spin(controller, 360, 20)

    assert controller.turns == [(180.0, 20), (180.0, 20)]
