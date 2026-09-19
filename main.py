"""Full stack: arbiter (priority mux + watchdog) + reflex thread + transcript-driven
voice-in + brain episodes + occupancy map WebSocket server, wired together. Verb
execution blocks per-episode (each verb self-completes before returning), and a wake
event lets a spoken command interrupt the idle wait between episodes so voice-in
feels real-time (CLAUDE.md sections 5-6).

STT is now local faster-whisper on the laptop (laptop/audio.py). Transcripts arrive
via the Pi-to-laptop TCP pipeline and are pushed into TranscriptBuffer by
pi/client.py. The brain loop consumes the latest final transcript each episode.
"""

import threading

from dotenv import load_dotenv

from brain.loop import run_episode
from brain.state import RobotState
from control.arbiter import Arbiter
from control.mapper import OccupancyMap
from control.map_server import MapServer
from control.pose import PoseEstimator
from control.reflex import ReflexLoop
from perception.camera import get_latest_detections
from perception.transcript import TranscriptBuffer

load_dotenv()

MAX_EPISODE_GAP_S = 1.0


def main() -> None:
    state = RobotState()
    wake_event = threading.Event()

    pose_estimator = PoseEstimator()
    mapper = OccupancyMap()
    transcript_buffer = TranscriptBuffer()

    arbiter = Arbiter(publish_cmd_vel=lambda linear, angular: None)
    threading.Thread(target=arbiter.run_forever, daemon=True).start()

    reflex = ReflexLoop(
        get_detections=get_latest_detections,
        arbiter=arbiter,
        pose_estimator=pose_estimator,
    )
    threading.Thread(target=reflex.run_forever, daemon=True).start()

    map_server = MapServer(mapper, lambda: pose_estimator.pose)
    threading.Thread(target=map_server.run_forever, daemon=True).start()

    while True:
        state = run_episode(state, arbiter, mapper, pose_estimator, transcript_buffer)
        wake_event.wait(timeout=MAX_EPISODE_GAP_S)
        wake_event.clear()


if __name__ == "__main__":
    main()
