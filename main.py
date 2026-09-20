"""Run direct commands or perceptual missions against one RoboMaster connection."""

import argparse
import asyncio
import logging

from dotenv import load_dotenv

load_dotenv()

from brain.loop import run_episode
from brain.backboard_client import brain
from brain.state import RobotState
from control.robomaster import RoboMasterController
from perception.vision import close_vision_client, vision_retry_delay, vision_unavailable_reason
from shared.inference import InferenceUnavailable

EPISODE_GAP_S = 1.0


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goal", required=True, help="direct robot command or autonomous mission")
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
                    state = await run_episode(state, controller)
                    if state.finished_goal is not None and state.finished_goal == state.current_goal:
                        break
                    if reason := vision_unavailable_reason():
                        raise InferenceUnavailable(reason)
                    delay = max(EPISODE_GAP_S, vision_retry_delay())
                    logging.getLogger(__name__).info("episode: next camera cycle in %.1fs", delay)
                    await asyncio.sleep(delay)
            except InferenceUnavailable as exc:
                logging.getLogger(__name__).error("Mission stopped: %s", exc)
                controller.stop()
    finally:
        try:
            await brain.aclose()
        finally:
            close_vision_client()


if __name__ == "__main__":
    asyncio.run(main())
