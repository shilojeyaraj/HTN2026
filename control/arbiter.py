"""Priority mux between the brain's low-priority intent and the reflex loop's
high-priority intent, with a watchdog that halts the robot if both go stale
(CLAUDE.md section 6)."""

import time

WATCHDOG_TIMEOUT_S = 0.5
PUBLISH_HZ = 30


class Arbiter:
    def __init__(self, publish_cmd_vel):
        self.publish_cmd_vel = publish_cmd_vel
        self._brain_cmd = (0.0, 0.0)
        self._brain_cmd_at = 0.0
        self._reflex_cmd: tuple[float, float] | None = None  # None = no override
        self._reflex_cmd_at = 0.0

    def set_brain_cmd(self, linear: float, angular: float) -> None:
        self._brain_cmd = (linear, angular)
        self._brain_cmd_at = time.monotonic()

    def set_reflex_cmd(self, cmd: tuple[float, float] | None) -> None:
        self._reflex_cmd = cmd
        self._reflex_cmd_at = time.monotonic()

    def tick(self) -> None:
        now = time.monotonic()
        if self._reflex_cmd is not None and now - self._reflex_cmd_at < WATCHDOG_TIMEOUT_S:
            linear, angular = self._reflex_cmd
        elif now - self._brain_cmd_at < WATCHDOG_TIMEOUT_S:
            linear, angular = self._brain_cmd
        else:
            linear, angular = (0.0, 0.0)  # both stale: halt
        self.publish_cmd_vel(linear, angular)

    def run_forever(self) -> None:
        period = 1.0 / PUBLISH_HZ
        while True:
            start = time.monotonic()
            self.tick()
            time.sleep(max(0.0, period - (time.monotonic() - start)))
