"""Full stack: arbiter (priority mux + watchdog) + reflex thread + brain episodes, wired
together. Verb execution blocks per-episode (each verb self-completes before returning),
so the deliberative loop is event-driven rather than a fixed ~1 Hz tick (CLAUDE.md
sections 5-6)."""

import threading
import time

from dotenv import load_dotenv

from brain.loop import run_episode
from brain.state import RobotState
from control.arbiter import Arbiter
from control.reflex import ReflexLoop
from perception.camera import get_latest_detections

load_dotenv()

MIN_EPISODE_GAP_S = 1.0


def main() -> None:
    state = RobotState()

    arbiter = Arbiter(publish_cmd_vel=lambda linear, angular: None)
    threading.Thread(target=arbiter.run_forever, daemon=True).start()

    reflex = ReflexLoop(get_detections=get_latest_detections, arbiter=arbiter)
    threading.Thread(target=reflex.run_forever, daemon=True).start()

    while True:
        start = time.monotonic()
        state = run_episode(state, arbiter)
        time.sleep(max(0.0, MIN_EPISODE_GAP_S - (time.monotonic() - start)))


if __name__ == "__main__":
    main()
