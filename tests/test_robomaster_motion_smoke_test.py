"""Check script sequencing offline; the standalone script itself uses real hardware."""

from unittest.mock import Mock, call

import pytest

import robomaster_motion_smoke_test as smoke


def test_physical_script_uses_requested_sequence_and_closes(monkeypatch):
    events = Mock()
    monkeypatch.setattr(smoke, "RoboMasterController", lambda: events.controller)
    monkeypatch.setattr(smoke.time, "sleep", events.sleep)

    smoke.main()

    assert events.mock_calls == [
        call.controller.connect(), call.controller.forward(0.25), call.sleep(1),
        call.controller.turn(45), call.controller.stop(), call.controller.close(),
    ]


@pytest.mark.parametrize("error", [RuntimeError("move rejected"), KeyboardInterrupt()])
def test_physical_script_closes_on_failure_or_interruption(error, monkeypatch):
    controller = Mock()
    controller.forward.side_effect = error
    monkeypatch.setattr(smoke, "RoboMasterController", lambda: controller)

    with pytest.raises(type(error)):
        smoke.main()

    controller.turn.assert_not_called()
    controller.close.assert_called_once()
