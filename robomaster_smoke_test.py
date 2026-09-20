"""Small physical RoboMaster EP Core smoke test. Run only on the robot's AP Wi-Fi."""

import logging

import cv2

from control.robomaster import RoboMasterController


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    controller = RoboMasterController()
    try:
        controller.connect()
        print("Connected to RoboMaster EP Core")
        controller.forward(1, xy_speed=2)
        controller.turn(30, z_speed=20)
        controller.stop()
        frame = controller.get_latest_frame()
        if frame is None:
            print("No camera frame received")
        elif cv2.imwrite("robomaster_test_frame.jpg", frame):
            print("Saved robomaster_test_frame.jpg")
        else:
            print("Camera frame received but could not be saved")
    finally:
        controller.close()


if __name__ == "__main__":
    main()
