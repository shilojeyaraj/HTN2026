"""Configurable physical RoboMaster EP Core motion and camera smoke test."""

import argparse
import logging
import math

import cv2

from control.robomaster import MAX_ROTATION_DEG, RoboMasterController


def _spin(controller: RoboMasterController, degrees: float, z_speed: float) -> None:
    """Turn by an arbitrary signed amount while retaining bounded SDK commands."""
    if not math.isfinite(degrees) or abs(degrees) > 720:
        raise ValueError("spin_degrees must be finite and no more than 720 degrees")
    remaining = degrees
    while remaining:
        step = max(-MAX_ROTATION_DEG, min(MAX_ROTATION_DEG, remaining))
        controller.turn(step, z_speed=z_speed)
        remaining -= step


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--forward-m", type=float, default=0.2)
    parser.add_argument("--xy-speed", type=float, default=0.5)
    parser.add_argument("--turn-degrees", type=float, default=30)
    parser.add_argument("--spin-degrees", type=float, default=0,
                        help="additional signed chassis rotation; 360 performs one full spin")
    parser.add_argument("--z-speed", type=float, default=20)
    parser.add_argument("--arm-x-mm", type=float, default=40,
                        help="relative arm extension; forward is positive")
    parser.add_argument("--arm-y-mm", type=float, default=30,
                        help="relative arm height; up is positive")
    parser.add_argument("--gripper-power", type=int, default=25)
    parser.add_argument("--gripper-dwell-s", type=float, default=0.5)
    parser.add_argument("--frame-path", default="robomaster_test_frame.jpg")
    parser.add_argument("--skip-chassis", action="store_true")
    parser.add_argument("--skip-arm", action="store_true")
    parser.add_argument("--skip-gripper", action="store_true")
    parser.add_argument("--skip-camera", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)
    controller = RoboMasterController()
    arm_moved = False
    try:
        controller.connect()
        print("Connected to RoboMaster EP Core")

        if not args.skip_chassis:
            controller.forward(args.forward_m, xy_speed=args.xy_speed)
            controller.turn(args.turn_degrees, z_speed=args.z_speed)
            _spin(controller, args.spin_degrees, args.z_speed)
            controller.stop()

        if not args.skip_arm:
            controller.recenter_arm()
            controller.move_arm(args.arm_x_mm, args.arm_y_mm)
            arm_moved = True

        if not args.skip_gripper:
            controller.open_gripper(power=args.gripper_power, dwell_s=args.gripper_dwell_s)
            controller.close_gripper(power=args.gripper_power, dwell_s=args.gripper_dwell_s)

        if not args.skip_camera:
            frame = controller.get_latest_frame()
            if frame is None:
                print("No camera frame received")
            elif cv2.imwrite(args.frame_path, frame):
                print(f"Saved {args.frame_path}")
            else:
                print("Camera frame received but could not be saved")

        if arm_moved:
            controller.recenter_arm()
            arm_moved = False
    finally:
        if arm_moved:
            try:
                controller.recenter_arm()
            except Exception:
                logging.exception("could not recenter arm during shutdown")
        controller.close()


if __name__ == "__main__":
    main()
