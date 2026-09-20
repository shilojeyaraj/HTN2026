"""Run deliberative robot episodes against one RoboMaster EP Core connection."""

import argparse
import time

from dotenv import load_dotenv

from brain.loop import run_episode
from brain.state import RobotState
from control.robomaster import RoboMasterController

load_dotenv()

EPISODE_GAP_S = 1.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--goal", required=True, help="mission for the planner to pursue")
    args = parser.parse_args()

    state = RobotState(current_goal=args.goal)
    with RoboMasterController() as controller:
        while True:
            state = run_episode(state, controller)
            time.sleep(EPISODE_GAP_S)


if __name__ == "__main__":
    main()
