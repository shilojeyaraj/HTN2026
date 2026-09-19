"""Full stack: arbiter (priority mux + watchdog) + reflex thread + transcript-driven
voice-in + brain episodes + occupancy map WebSocket server, wired together. Verb
execution blocks per-episode (each verb self-completes before returning), and a wake
event lets a spoken command interrupt the idle wait between episodes so voice-in
feels real-time (CLAUDE.md sections 5-6).

The USB webcam pipeline (pi/client.py) streams video + audio to the laptop over TCP.
Depth results and transcripts from the laptop are pushed into the shared DepthBuffer
and TranscriptBuffer respectively. The reflex loop reads detections from
perception/camera.py (which merges ultrasonic + depth). The brain loop reads
frames and detections for vision and planning. Motor commands go through the
arbiter to the motor driver (control/motors.py).
"""

import logging
import os
import threading

from dotenv import load_dotenv

from brain.loop import run_episode
from brain.state import RobotState
from control.arbiter import Arbiter
from control.mapper import OccupancyMap
from control.map_server import MapServer
from control.motors import MotorDriver
from control.pose import PoseEstimator
from control.reflex import ReflexLoop
from perception.camera import get_latest_detections
from perception.depth_buffer import get_buffer as get_depth_buffer
from perception.transcript import TranscriptBuffer

load_dotenv()

MAX_EPISODE_GAP_S = 1.0

logger = logging.getLogger(__name__)


def main() -> None:
    state = RobotState()
    wake_event = threading.Event()

    pose_estimator = PoseEstimator()
    mapper = OccupancyMap()
    transcript_buffer = TranscriptBuffer()
    depth_buffer = get_depth_buffer()

    # Motor driver: real GPIO PWM on the Pi, no-op on Mac/dev
    motors = MotorDriver()

    # Start the USB webcam + mic streaming pipeline to the laptop.
    # Depth results -> depth_buffer, transcripts -> transcript_buffer,
    # JPEG frames -> depth_buffer (for the brain's vision step).
    try:
        from pi.client import start_streaming
        start_streaming(
            host=os.environ.get("DEPTH_SERVER_HOST", "127.0.0.1"),
            port=int(os.environ.get("DEPTH_SERVER_PORT", "8765")),
            video_device=os.environ.get("VIDEO_DEVICE", "/dev/video0"),
            audio_device=os.environ.get("AUDIO_DEVICE", "default"),
            on_depth=depth_buffer.push_depth,
            on_transcript=lambda text, uid: transcript_buffer.push(text, final=True, utterance_id=uid),
            on_frame=depth_buffer.push_frame,
        )
        logger.info("USB webcam pipeline started")
    except Exception:
        logger.warning("USB webcam pipeline not started — running without camera/depth", exc_info=True)

    arbiter = Arbiter(publish_cmd_vel=motors.publish_cmd_vel)
    threading.Thread(target=arbiter.run_forever, daemon=True).start()

    reflex = ReflexLoop(
        get_detections=get_latest_detections,
        arbiter=arbiter,
        pose_estimator=pose_estimator,
    )
    threading.Thread(target=reflex.run_forever, daemon=True).start()

    map_server = MapServer(mapper, lambda: pose_estimator.pose)
    threading.Thread(target=map_server.run_forever, daemon=True).start()

    # Push-to-talk (optional, if GPIO button is wired)
    try:
        from voice.push_to_talk import PushToTalkLoop
        ptt = PushToTalkLoop(state, wake_event)
        threading.Thread(target=ptt.run_forever, daemon=True).start()
        logger.info("Push-to-talk loop started on GPIO pin 17")
    except Exception:
        logger.info("Push-to-talk not available — using laptop transcription only")

    while True:
        state = run_episode(state, arbiter, mapper, pose_estimator, transcript_buffer)
        wake_event.wait(timeout=MAX_EPISODE_GAP_S)
        wake_event.clear()


if __name__ == "__main__":
    main()
