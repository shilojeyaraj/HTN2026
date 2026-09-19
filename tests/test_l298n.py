from control.l298n import L298NConfig, L298NDrive, _Channel


class FakeOutput:
    def __init__(self):
        self.history = []
        self._value = 0

    @property
    def value(self):
        return self._value

    @value.setter
    def value(self, value):
        self._value = value
        self.history.append(value)

    def on(self):
        self.value = 1

    def off(self):
        self.value = 0


class FakeEncoder:
    def __init__(self):
        self.steps = 0


def make_drive(turn_units_per_degree=2.0):
    left_pins = [FakeOutput() for _ in range(3)]
    right_pins = [FakeOutput() for _ in range(3)]
    left = _Channel(*left_pins)
    right = _Channel(*right_pins)
    left_encoder = FakeEncoder()
    right_encoder = FakeEncoder()

    def sleep(_):
        if left_pins[0].value:
            left_encoder.steps += 5
        if right_pins[0].value:
            right_encoder.steps += 5

    drive = L298NDrive(
        L298NConfig(turn_units_per_degree=turn_units_per_degree),
        left,
        right,
        left_encoder,
        right_encoder,
        sleep=sleep,
    )
    return drive, left_pins, right_pins


def test_forward_stops_each_side_at_encoder_target():
    drive, left, right = make_drive()

    result = drive.forward(10)

    assert result["status"] == "completed"
    assert result["left_encoder_units"] == result["right_encoder_units"] == 10
    assert 0.45 in left[0].history and 0.45 in right[0].history
    assert 1 in left[1].history and 1 in right[1].history
    assert left[0].value == right[0].value == 0


def test_clockwise_drives_left_forward_and_right_backward():
    drive, left, right = make_drive()

    result = drive.turn_clockwise(5)

    assert result["status"] == "completed"
    assert result["target_encoder_units"] == 10
    assert 1 in left[1].history  # left IN1: forward
    assert 1 in right[2].history  # right IN2: backward


def test_counterclockwise_drives_left_backward_and_right_forward():
    drive, left, right = make_drive()

    result = drive.turn_counterclockwise(5)

    assert result["status"] == "completed"
    assert 1 in left[2].history  # left IN2: backward
    assert 1 in right[1].history  # right IN1: forward
