"""The only module that talks to the DJI RoboMaster SDK."""

from __future__ import annotations

import logging
import math
import queue
import threading
import time

logger = logging.getLogger(__name__)

DEFAULT_XY_SPEED_MPS = 0.5
DEFAULT_Z_SPEED_DPS = 30.0
MAX_TRANSLATION_M = 1.0
MAX_ROTATION_DEG = 180.0
MAX_ARM_DELTA_MM = 80.0
DEFAULT_GRIPPER_POWER = 25
DEFAULT_GRIPPER_DWELL_S = 0.5
CAMERA_WARMUP_S = 0.3
CAMERA_RETRIES = 3


class RoboMasterError(RuntimeError):
    """A RoboMaster command could not be completed safely."""


def _telemetry_tuple(*values) -> tuple:
    return tuple(values[0]) if len(values) == 1 and isinstance(values[0], (tuple, list)) else tuple(values)


class RoboMasterController:
    """One AP-mode RoboMaster connection, shared by all robot tools."""

    def __init__(self, *, robot_factory=None, camera_module=None, sleep=time.sleep):
        self._robot_factory = robot_factory
        self._camera_module = camera_module
        self._sleep = sleep
        self._lock = threading.RLock()
        self._ep = None
        self._chassis = None
        self._camera = None
        self._sensor = None
        self._robotic_arm = None
        self._gripper = None
        self._camera_started = False
        self._camera_start_attempted = False
        self._position_m = None
        self._attitude_deg = None
        self._velocity_mps = None
        self._status = None
        self._tof_mm = None

    @property
    def chassis(self):
        self._require_connected()
        return self._chassis

    @property
    def camera(self):
        self._require_connected()
        return self._camera

    @property
    def robotic_arm(self):
        return self._require_module(self._robotic_arm, "robotic arm")

    @property
    def gripper(self):
        return self._require_module(self._gripper, "gripper")

    def connect(self) -> "RoboMasterController":
        """Connect once to the robot's access point and subscribe to real telemetry."""
        with self._lock:
            if self._ep is not None:
                return self
            ep = None
            try:
                if self._robot_factory is None:
                    from robomaster import camera, robot

                    self._robot_factory = robot.Robot
                    self._camera_module = camera
                ep = self._robot_factory()
                if ep.initialize(conn_type="ap") is False:
                    raise RoboMasterError("RoboMaster SDK could not initialize AP mode")
                self._ep = ep
                self._chassis = ep.chassis
                self._camera = ep.camera
                self._sensor = getattr(ep, "sensor", None)
                self._robotic_arm = getattr(ep, "robotic_arm", None)
                self._gripper = getattr(ep, "gripper", None)
                self._subscribe_telemetry()
                logger.info("connected to RoboMaster EP Core in AP mode")
                return self
            except Exception as exc:
                self._stop_safely(chassis=getattr(ep, "chassis", None))
                if ep is not None:
                    try:
                        ep.close()
                    except Exception:
                        logger.debug("RoboMaster cleanup after failed connect also failed", exc_info=True)
                self._ep = self._chassis = self._camera = self._sensor = None
                self._robotic_arm = self._gripper = None
                raise RoboMasterError(f"failed to connect to RoboMaster: {exc}") from exc

    def _subscribe_telemetry(self) -> None:
        subscriptions = (
            (self._chassis, "sub_position", self._on_position),
            (self._chassis, "sub_attitude", self._on_attitude),
            (self._chassis, "sub_velocity", self._on_velocity),
            (self._chassis, "sub_status", self._on_status),
            (self._sensor, "sub_distance", self._on_tof),
        )
        for source, name, callback in subscriptions:
            subscribe = getattr(source, name, None)
            if subscribe is None:
                continue
            try:
                subscribe(freq=5, callback=callback)
            except Exception:
                logger.warning("RoboMaster telemetry subscription %s failed", name, exc_info=True)

    def _on_position(self, *position) -> None:
        with self._lock:
            self._position_m = _telemetry_tuple(*position)

    def _on_attitude(self, *attitude) -> None:
        with self._lock:
            self._attitude_deg = _telemetry_tuple(*attitude)

    def _on_velocity(self, *velocity) -> None:
        with self._lock:
            self._velocity_mps = _telemetry_tuple(*velocity)

    def _on_status(self, *status) -> None:
        with self._lock:
            self._status = _telemetry_tuple(*status)

    def _on_tof(self, *distances) -> None:
        with self._lock:
            self._tof_mm = _telemetry_tuple(*distances)

    def get_chassis_state(self) -> dict:
        """Return only telemetry actually received from the RoboMaster."""
        self._require_connected()
        with self._lock:
            state = {}
            if self._position_m is not None:
                state["position_m"] = self._position_m
            if self._attitude_deg is not None:
                state["attitude_deg"] = self._attitude_deg
            if self._velocity_mps is not None:
                state["velocity_mps"] = self._velocity_mps
            if self._status is not None:
                state["status"] = self._status
            return state

    def get_tof_distances(self) -> dict:
        """Return raw onboard ToF readings in millimetres, without guessed bearings."""
        self._require_connected()
        with self._lock:
            return {"tof_mm": self._tof_mm}

    def forward(self, meters: float, *, xy_speed: float = DEFAULT_XY_SPEED_MPS) -> dict:
        return self._move(x=self._distance(meters), xy_speed=xy_speed)

    def backward(self, meters: float, *, xy_speed: float = DEFAULT_XY_SPEED_MPS) -> dict:
        return self._move(x=-self._distance(meters), xy_speed=xy_speed)

    def strafe_left(self, meters: float, *, xy_speed: float = DEFAULT_XY_SPEED_MPS) -> dict:
        return self._move(y=self._distance(meters), xy_speed=xy_speed)

    def strafe_right(self, meters: float, *, xy_speed: float = DEFAULT_XY_SPEED_MPS) -> dict:
        return self._move(y=-self._distance(meters), xy_speed=xy_speed)

    def turn(self, degrees: float, *, z_speed: float = DEFAULT_Z_SPEED_DPS) -> dict:
        if not isinstance(degrees, (int, float)) or not math.isfinite(degrees) or not degrees:
            raise ValueError("degrees must be a non-zero finite number")
        if abs(degrees) > MAX_ROTATION_DEG:
            raise ValueError(f"degrees must be no more than {MAX_ROTATION_DEG}")
        return self._move(z=degrees, z_speed=z_speed)

    def _distance(self, meters: float) -> float:
        if not isinstance(meters, (int, float)) or not math.isfinite(meters) or meters <= 0:
            raise ValueError("meters must be a positive finite number")
        if meters > MAX_TRANSLATION_M:
            raise ValueError(f"meters must be no more than {MAX_TRANSLATION_M}")
        return meters

    def _move(self, *, x: float = 0, y: float = 0, z: float = 0,
              xy_speed: float = DEFAULT_XY_SPEED_MPS, z_speed: float = DEFAULT_Z_SPEED_DPS) -> dict:
        if not 0.5 <= xy_speed <= 2:
            raise ValueError("xy_speed must be in [0.5, 2]")
        if not 10 <= z_speed <= 540:
            raise ValueError("z_speed must be in [10, 540]")
        try:
            self.chassis.move(x=x, y=y, z=z, xy_speed=xy_speed, z_speed=z_speed).wait_for_completed()
            return {"status": "completed"}
        except Exception as exc:
            self._stop_safely()
            logger.exception("RoboMaster movement failed; stop requested")
            raise RoboMasterError(f"RoboMaster movement failed: {exc}") from exc

    def stop(self) -> dict:
        try:
            self.chassis.drive_speed(x=0, y=0, z=0)
            return {"status": "completed"}
        except Exception as exc:
            logger.exception("RoboMaster stop command failed")
            raise RoboMasterError(f"RoboMaster stop failed: {exc}") from exc

    def move_arm(self, x_mm: float = 0, y_mm: float = 0) -> dict:
        """Move the arm relative to its current position: forward/up are positive."""
        x_mm = self._arm_delta("x_mm", x_mm)
        y_mm = self._arm_delta("y_mm", y_mm)
        if not x_mm and not y_mm:
            raise ValueError("move_arm requires a non-zero x_mm or y_mm")
        try:
            self.robotic_arm.move(x=x_mm, y=y_mm).wait_for_completed()
            return {"status": "completed"}
        except Exception as exc:
            self._stop_arm_safely()
            logger.exception("RoboMaster arm movement failed")
            raise RoboMasterError(f"RoboMaster arm movement failed: {exc}") from exc

    def recenter_arm(self) -> dict:
        try:
            self.robotic_arm.recenter().wait_for_completed()
            return {"status": "completed"}
        except Exception as exc:
            self._stop_arm_safely()
            logger.exception("RoboMaster arm recenter failed")
            raise RoboMasterError(f"RoboMaster arm recenter failed: {exc}") from exc

    def open_gripper(self, *, power: int = DEFAULT_GRIPPER_POWER,
                     dwell_s: float = DEFAULT_GRIPPER_DWELL_S) -> dict:
        return self._actuate_gripper("open", power, dwell_s)

    def close_gripper(self, *, power: int = DEFAULT_GRIPPER_POWER,
                      dwell_s: float = DEFAULT_GRIPPER_DWELL_S) -> dict:
        return self._actuate_gripper("close", power, dwell_s)

    def _arm_delta(self, name: str, value: float) -> float:
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"{name} must be a finite number")
        if abs(value) > MAX_ARM_DELTA_MM:
            raise ValueError(f"{name} must be no more than {MAX_ARM_DELTA_MM} mm per move")
        return float(value)

    def _actuate_gripper(self, command: str, power: int, dwell_s: float) -> dict:
        if not isinstance(power, int) or not 1 <= power <= 100:
            raise ValueError("gripper power must be an integer in [1, 100]")
        if not isinstance(dwell_s, (int, float)) or not math.isfinite(dwell_s) or dwell_s <= 0:
            raise ValueError("gripper dwell_s must be a positive finite number")
        try:
            if getattr(self.gripper, command)(power=power) is False:
                raise RoboMasterError(f"RoboMaster gripper {command} command was rejected")
            self._sleep(dwell_s)
            return {"status": "completed"}
        except RoboMasterError:
            raise
        except Exception as exc:
            logger.exception("RoboMaster gripper %s failed", command)
            raise RoboMasterError(f"RoboMaster gripper {command} failed: {exc}") from exc
        finally:
            self._pause_gripper_safely()

    def _start_camera(self) -> bool:
        with self._lock:
            if self._camera_start_attempted:
                return self._camera_started
            self._camera_start_attempted = True
            try:
                self.camera.start_video_stream(
                    display=False,
                    resolution=self._camera_module.STREAM_360P,
                )
            except TypeError:
                # Older SDK releases do not accept resolution but still provide 360p.
                self.camera.start_video_stream(display=False)
            self._camera_started = True
        self._sleep(CAMERA_WARMUP_S)
        return True

    def get_latest_frame(self, *, retries: int = CAMERA_RETRIES, timeout: float = 1.0,
                         strategy: str = "newest"):
        """Return the newest OpenCV frame, or None after transient stream failures."""
        if retries < 1 or timeout <= 0:
            raise ValueError("retries and timeout must be positive")
        try:
            if not self._start_camera():
                return None
        except Exception:
            logger.warning("RoboMaster camera startup failed", exc_info=True)
            return None
        for attempt in range(retries):
            try:
                frame = self.camera.read_cv2_image(timeout=timeout, strategy=strategy)
            except queue.Empty:
                logger.debug("RoboMaster camera queue empty (%d/%d)", attempt + 1, retries)
                frame = None
            except Exception:
                logger.warning("RoboMaster camera read failed (%d/%d)", attempt + 1, retries, exc_info=True)
                frame = None
            if frame is not None:
                return frame
            if attempt + 1 < retries:
                self._sleep(0.05)
        return None

    def _require_connected(self):
        if self._ep is None:
            raise RoboMasterError("RoboMaster is not connected; call connect() once at startup")
        return self._ep

    def _require_module(self, module, name: str):
        self._require_connected()
        if module is None:
            raise RoboMasterError(f"RoboMaster {name} module is unavailable")
        return module

    def _stop_safely(self, chassis=None) -> None:
        try:
            (chassis or self._chassis).drive_speed(x=0, y=0, z=0)
        except Exception:
            logger.debug("best-effort RoboMaster stop failed", exc_info=True)

    def _stop_arm_safely(self) -> None:
        try:
            self.robotic_arm.stop()
        except Exception:
            logger.debug("best-effort RoboMaster arm stop failed", exc_info=True)

    def _pause_gripper_safely(self, gripper=None) -> None:
        try:
            (gripper or self._gripper).pause()
        except Exception:
            logger.debug("best-effort RoboMaster gripper pause failed", exc_info=True)

    def close(self) -> None:
        """Stop motion, stop video, unsubscribe telemetry, and release the SDK connection."""
        with self._lock:
            ep, chassis, camera, sensor, gripper = (
                self._ep, self._chassis, self._camera, self._sensor, self._gripper,
            )
            camera_started = self._camera_started
            self._ep = self._chassis = self._camera = self._sensor = None
            self._robotic_arm = self._gripper = None
            self._camera_started = False
            self._camera_start_attempted = False
        if ep is None:
            return
        self._stop_safely(chassis)
        self._pause_gripper_safely(gripper)
        if camera_started:
            try:
                camera.stop_video_stream()
            except Exception:
                logger.warning("RoboMaster camera shutdown failed", exc_info=True)
        for source, name in (
            (chassis, "unsub_position"), (chassis, "unsub_attitude"),
            (chassis, "unsub_velocity"), (chassis, "unsub_status"),
            (sensor, "unsub_distance"),
        ):
            unsubscribe = getattr(source, name, None)
            if unsubscribe is not None:
                try:
                    unsubscribe()
                except Exception:
                    logger.debug("RoboMaster telemetry cleanup %s failed", name, exc_info=True)
        try:
            ep.close()
        except Exception:
            logger.warning("RoboMaster SDK shutdown failed", exc_info=True)

    def __enter__(self) -> "RoboMasterController":
        return self.connect()

    def __exit__(self, *_exc_info) -> None:
        self.close()
