"""Physical loaner-robot test: forward 0.25 m, pause, turn 45 degrees, stop.

Run explicitly: python robomaster_motion_smoke_test.py
Uses the application's real RoboMasterController and configured STA connection.
"""

import logging
import time

from control.robomaster import RoboMasterController


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    controller = RoboMasterController()
    try:
        controller.connect()
        logging.info("Connected to the physical RoboMaster; starting chassis test")
        controller.forward(0.25)
        time.sleep(1)
        controller.turn(45)
        controller.stop()
        logging.info("Chassis test completed; confirm observed movement against the SDK action logs")
    finally:
        controller.close()


if __name__ == "__main__":
    main()
