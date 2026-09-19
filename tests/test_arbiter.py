"""Unit tests for the arbiter (control/arbiter.py).

Pure logic, no network. Verifies priority mux (reflex > brain), watchdog
timeout (both stale -> halt), and that the publish callback receives the
correct (linear, angular) tuples.
"""

import time
from unittest.mock import MagicMock

from control.arbiter import Arbiter, WATCHDOG_TIMEOUT_S


class TestArbiterPriority:
    def test_brain_command_published_when_no_reflex(self):
        pub = MagicMock()
        arb = Arbiter(pub)
        arb.set_brain_cmd(0.3, 0.0)
        arb.tick()
        pub.assert_called_once_with(0.3, 0.0)

    def test_reflex_overrides_brain(self):
        pub = MagicMock()
        arb = Arbiter(pub)
        arb.set_brain_cmd(0.3, 0.0)
        arb.set_reflex_cmd((0.0, 0.0))
        arb.tick()
        pub.assert_called_once_with(0.0, 0.0)

    def test_brain_resumes_after_reflex_clears(self):
        pub = MagicMock()
        arb = Arbiter(pub)
        arb.set_brain_cmd(0.3, 0.0)
        arb.set_reflex_cmd((0.0, 0.0))
        arb.tick()
        arb.set_reflex_cmd(None)
        arb.tick()
        assert pub.call_args_list[-1] == ((0.3, 0.0),)


class TestArbiterWatchdog:
    def test_halts_when_brain_stale(self):
        pub = MagicMock()
        arb = Arbiter(pub)
        arb.set_brain_cmd(0.3, 0.0)
        time.sleep(WATCHDOG_TIMEOUT_S + 0.05)
        arb.tick()
        pub.assert_called_once_with(0.0, 0.0)

    def test_halts_when_both_stale(self):
        pub = MagicMock()
        arb = Arbiter(pub)
        arb.set_brain_cmd(0.3, 0.0)
        arb.set_reflex_cmd((0.0, 0.0))
        time.sleep(WATCHDOG_TIMEOUT_S + 0.05)
        arb.tick()
        pub.assert_called_once_with(0.0, 0.0)

    def test_reflex_still_active_after_brain_stale(self):
        pub = MagicMock()
        arb = Arbiter(pub)
        arb.set_brain_cmd(0.3, 0.0)
        time.sleep(WATCHDOG_TIMEOUT_S + 0.05)
        arb.set_reflex_cmd((0.0, 0.0))
        arb.tick()
        pub.assert_called_once_with(0.0, 0.0)


class TestArbiterInitial:
    def test_publishes_zero_before_any_command(self):
        pub = MagicMock()
        arb = Arbiter(pub)
        arb.tick()
        pub.assert_called_once_with(0.0, 0.0)
