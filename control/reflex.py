"""Fast onboard safety loop: ~30 Hz, classical, no network. Publishes a high-priority
override into the arbiter when an obstacle is too close; otherwise lets the brain's
command through (CLAUDE.md section 6)."""

import time

STOP_DISTANCE_M = 0.3
LOOP_HZ = 30


class ReflexLoop:
    def __init__(self, get_detections, arbiter):
        self.get_detections = get_detections
        self.arbiter = arbiter

    def tick(self) -> None:
        detections = self.get_detections()
        blocked = any(abs(d["bearing_deg"]) < 30 and d["distance_m"] < STOP_DISTANCE_M for d in detections)
        self.arbiter.set_reflex_cmd((0.0, 0.0) if blocked else None)

    def run_forever(self) -> None:
        period = 1.0 / LOOP_HZ
        while True:
            start = time.monotonic()
            self.tick()
            time.sleep(max(0.0, period - (time.monotonic() - start)))
