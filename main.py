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
from perception.vision import aclose_vision_client
from shared.inference import InferenceUnavailable

async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goal", help="direct command or mission; omit to scan once, then monitor")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    state = RobotState(current_goal=args.goal)
    try:
        with RoboMasterController() as controller:
            try:
                while True:
                    if not args.goal and (not STARTUP_SCAN_ENABLED or state.startup_scan_status == "completed"):
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
                logging.getLogger(__name__).error("Mission stopped: %s", exc)
                controller.stop()
    finally:
        try:
            await brain.aclose()
        finally:
            await aclose_vision_client()


if __name__ == "__main__":
    asyncio.run(main())
