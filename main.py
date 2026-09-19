"""Full stack: arbiter (priority mux + watchdog) + reflex thread + push-to-talk voice-in
+ brain episodes, wired together. Verb execution blocks per-episode (each verb
self-completes before returning), and a wake event lets a spoken command interrupt the
idle wait between episodes so voice-in feels real-time (CLAUDE.md sections 5-6)."""

import threading

from dotenv import load_dotenv

from brain.loop import run_episode
from brain.state import RobotState
from control.arbiter import Arbiter
from control.reflex import ReflexLoop
from perception.camera import get_latest_detections
from voice.push_to_talk import PushToTalkLoop

load_dotenv()

MAX_EPISODE_GAP_S = 1.0


def main() -> None:
    state = RobotState()
    wake_event = threading.Event()

    arbiter = Arbiter(publish_cmd_vel=lambda linear, angular: None)
    threading.Thread(target=arbiter.run_forever, daemon=True).start()

    reflex = ReflexLoop(get_detections=get_latest_detections, arbiter=arbiter)
    threading.Thread(target=reflex.run_forever, daemon=True).start()

    push_to_talk = PushToTalkLoop(state=state, wake_event=wake_event)
    threading.Thread(target=push_to_talk.run_forever, daemon=True).start()

    while True:
        state = run_episode(state, arbiter)
        wake_event.wait(timeout=MAX_EPISODE_GAP_S)
        wake_event.clear()


if __name__ == "__main__":
    main()
