"""Run direct commands or perceptual missions against one RoboMaster connection."""

import argparse
import asyncio
import logging
import time

from dotenv import load_dotenv

load_dotenv()

from brain.loop import run_episode
from brain.config import STARTUP_SCAN_ENABLED
from brain.backboard_client import brain
from brain.state import RobotState
from control.robomaster import RoboMasterController
from control.map_server import MapServer
from control.telemetry import rover_snapshot
from perception.vision import aclose_vision_client
from shared.inference import InferenceUnavailable

async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goal", help="direct command or mission; omit to scan once, then monitor")
    parser.add_argument("--telemetry-host", default="0.0.0.0", help="dashboard WebSocket bind address")
    parser.add_argument("--telemetry-port", type=int, default=8766, help="dashboard WebSocket port")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    state = RobotState(current_goal=args.goal)
    controller = RoboMasterController()
    server = MapServer(get_snapshot=lambda: rover_snapshot(controller, state))
    state.telemetry.update(goal=args.goal, phase="connecting", reason="Connecting to RoboMaster")
    try:
        server.start(args.telemetry_host, args.telemetry_port)
        with controller:
            state.telemetry.update(phase="idle", reason="Starting mission" if args.goal else
                                   ("Starting scan" if STARTUP_SCAN_ENABLED else "Monitoring"))
            try:
                while True:
                    if not args.goal and (not STARTUP_SCAN_ENABLED or state.startup_scan_status == "completed"):
                        state.telemetry.update(phase="idle", reason="Monitoring")
                        await asyncio.sleep(0.2)
                        continue
                    state = await run_episode(state, controller)
                    if state.finished_goal is not None and state.finished_goal == state.current_goal:
                        break
                    delay = max(0.0, state.retry_at - time.monotonic())
                    if delay:
                        logging.getLogger(__name__).info("episode: transient failure; retry in %.2fs", delay)
                        await asyncio.sleep(delay)
            except InferenceUnavailable as exc:
                state.telemetry.update(phase="failed", reason=str(exc))
                logging.getLogger(__name__).error("Mission stopped: %s", exc)
                controller.stop()
    except BaseException as exc:
        state.telemetry.update(phase="failed", reason=str(exc) or "Mission interrupted")
        raise
    finally:
        server.close()
        try:
            await brain.aclose()
        finally:
            await aclose_vision_client()


if __name__ == "__main__":
    asyncio.run(main())
