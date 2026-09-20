"""Run deliberative robot episodes against one RoboMaster EP Core connection."""

import argparse
import asyncio
import logging

from dotenv import load_dotenv

load_dotenv()

from brain.loop import run_episode
from brain.backboard_client import brain
from brain.state import RobotState
from control.robomaster import RoboMasterController
from perception.vision import close_vision_client

EPISODE_GAP_S = 1.0


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goal", required=True, help="mission for the planner to pursue")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    state = RobotState(current_goal=args.goal)
    try:
        with RoboMasterController() as controller:
            while True:
                state = await run_episode(state, controller)
                await asyncio.sleep(EPISODE_GAP_S)
    finally:
        try:
            await brain.aclose()
        finally:
            close_vision_client()


if __name__ == "__main__":
    asyncio.run(main())
