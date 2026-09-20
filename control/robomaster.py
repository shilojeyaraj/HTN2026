"""The only module that talks to the DJI RoboMaster SDK."""

from __future__ import annotations

import logging
import math
import queue
import threading
import time
from collections import deque

from av.error import InvalidDataError

logger = logging.getLogger(__name__)

DEFAULT_XY_SPEED_MPS = 0.7
DEFAULT_Z_SPEED_DPS = 90.0
MAX_TRANSLATION_M = 1.0
MAX_ROTATION_DEG = 180.0
MAX_ARM_DELTA_MM = 80.0
DEFAULT_GRIPPER_POWER = 25
DEFAULT_GRIPPER_DWELL_S = 0.5
CAMERA_READ_TIMEOUT_S = 0.25
CAMERA_MAX_FRAME_AGE_S = 1.0
CAMERA_RESTART_AFTER_S = 2.0
CAMERA_RESTART_DELAY_S = 0.5
CAMERA_SHUTDOWN_TIMEOUT_S = 5.0


class RoboMasterError(RuntimeError):
    """A RoboMaster command could not be completed safely."""


def _telemetry_tuple(*values) -> tuple:
    return tuple(values[0]) if len(values) == 1 and isinstance(values[0], (tuple, list)) else tuple(values)


class RoboMasterController:
    """One STA-mode RoboMaster connection, shared by all robot tools."""

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
        self._camera_lock = threading.Lock()
        self._camera_thread = None
        self._camera_stop = threading.Event()
        self._latest_frame = None
        self._frame_received_at = None
        self._decode_times = deque()
        self._decode_failures = 0
        self._stream_restarts = 0
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
        """Connect once to the robot over STA Wi-Fi and subscribe to real telemetry."""
        with self._lock:
            if self._ep is not None:
                return self
            if self._camera_thread is not None:
                if self._camera_thread.is_alive():
                    raise RoboMasterError("previous camera reader is still shutting down")
                self._camera_thread = None
            self._camera_stop.clear()
            ep = None
            try:
                if self._robot_factory is None:
                    from robomaster import camera, robot

                    self._robot_factory = robot.Robot
                    self._camera_module = camera
                ep = self._robot_factory()
                if ep.initialize(conn_type="sta") is False:
                    raise RoboMasterError("RoboMaster SDK could not initialize STA mode")
                self._ep = ep
                self._chassis = ep.chassis
                self._camera = ep.camera
                self._sensor = getattr(ep, "sensor", None)
                self._robotic_arm = getattr(ep, "robotic_arm", None)
                self._gripper = getattr(ep, "gripper", None)
                self._subscribe_telemetry()
                logger.info("connected to RoboMaster EP Core in STA mode; robot_type=%s chassis_type=%s",
                            type(ep), type(self._chassis))
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
        return self._move("forward", x=self._distance(meters), xy_speed=xy_speed)

    def backward(self, meters: float, *, xy_speed: float = DEFAULT_XY_SPEED_MPS) -> dict:
        return self._move("backward", x=-self._distance(meters), xy_speed=xy_speed)

    def strafe_left(self, meters: float, *, xy_speed: float = DEFAULT_XY_SPEED_MPS) -> dict:
        return self._move("strafe_left", y=self._distance(meters), xy_speed=xy_speed)

    def strafe_right(self, meters: float, *, xy_speed: float = DEFAULT_XY_SPEED_MPS) -> dict:
        return self._move("strafe_right", y=-self._distance(meters), xy_speed=xy_speed)

    def turn(self, degrees: float, *, z_speed: float = DEFAULT_Z_SPEED_DPS) -> dict:
        if not isinstance(degrees, (int, float)) or not math.isfinite(degrees) or not degrees:
            raise ValueError("degrees must be a non-zero finite number")
        if abs(degrees) > MAX_ROTATION_DEG:
            raise ValueError(f"degrees must be no more than {MAX_ROTATION_DEG}")
        return self._move("turn", z=degrees, z_speed=z_speed)

    def _distance(self, meters: float) -> float:
        if not isinstance(meters, (int, float)) or not math.isfinite(meters) or meters <= 0:
            raise ValueError("meters must be a positive finite number")
        if meters > MAX_TRANSLATION_M:
            raise ValueError(f"meters must be no more than {MAX_TRANSLATION_M}")
        return meters

    def _move(self, action: str, *, x: float = 0, y: float = 0, z: float = 0,
              xy_speed: float = DEFAULT_XY_SPEED_MPS, z_speed: float = DEFAULT_Z_SPEED_DPS) -> dict:
        if not 0.5 <= xy_speed <= 2:
            raise ValueError("xy_speed must be in [0.5, 2]")
        if not 10 <= z_speed <= 540:
            raise ValueError("z_speed must be in [10, 540]")
        started = time.monotonic()
        try:
            logger.info(
                "chassis action=%s starting: x=%.2fm y=%.2fm z=%.1fdeg xy_speed=%.2fm/s z_speed=%.1fdeg/s",
                action, x, y, z, xy_speed, z_speed,
            )
            sdk_action = self.chassis.move(x=x, y=y, z=z, xy_speed=xy_speed, z_speed=z_speed)
            self._wait_for_action(action, sdk_action)
            logger.info(
                "chassis action=%s completed duration_s=%.2f; telemetry=%s",
                action, time.monotonic() - started, self.get_chassis_state(),
            )
            return {"status": "completed"}
        except Exception as exc:
            self._stop_safely()
            logger.exception("chassis action=%s failed duration_s=%.2f; stop requested",
                             action, time.monotonic() - started)
            raise RoboMasterError(f"RoboMaster movement failed: {exc}") from exc

    def _wait_for_action(self, name: str, action) -> None:
        """SDK 'completed' includes rejected/failed actions; require actual success."""
        logger.info("SDK action=%s type=%s repr=%r state=%r", name, type(action), action,
                    getattr(action, "state", None))
        started = time.monotonic()
        wait_result = None
        try:
            wait_result = action.wait_for_completed()
        finally:
            logger.info(
                "SDK action=%s wait_for_completed=%r elapsed_s=%.3f repr=%r "
                "state=%r is_completed=%r has_succeeded=%r has_failed=%r failure_reason=%r",
                name, wait_result, time.monotonic() - started, action,
                getattr(action, "state", None), getattr(action, "is_completed", None),
                getattr(action, "has_succeeded", None), getattr(action, "has_failed", None),
                getattr(action, "failure_reason", None),
            )
        if wait_result is not True or getattr(action, "has_succeeded", None) is not True:
            raise RoboMasterError(
                f"{name} SDK action did not succeed: wait_result={wait_result!r}, "
                f"state={getattr(action, 'state', None)!r}, "
                f"failure_reason={getattr(action, 'failure_reason', None)!r}"
            )

    def stop(self) -> dict:
        try:
            logger.info("chassis stop requested")
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
            self._wait_for_action("move_arm", self.robotic_arm.move(x=x_mm, y=y_mm))
            return {"status": "completed"}
        except Exception as exc:
            self._stop_arm_safely()
            logger.exception("RoboMaster arm movement failed")
            raise RoboMasterError(f"RoboMaster arm movement failed: {exc}") from exc

    def recenter_arm(self) -> dict:
        try:
            self._wait_for_action("recenter_arm", self.robotic_arm.recenter())
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

    def start_camera(self) -> None:
        """Launch one reader; all video startup/decoding/recovery happens there."""
        with self._lock:
            self._require_connected()
            if self._camera_thread is not None:
                if self._camera_stop.is_set():
                    raise RoboMasterError("camera reader is still shutting down")
                return
            self._camera_stop.clear()
            self._camera_thread = threading.Thread(
                target=self._read_camera, args=(self.camera, self._camera_module.STREAM_360P),
                name="robomaster-frame-reader", daemon=True,
            )
            self._camera_thread.start()

    def _read_camera(self, camera, resolution) -> None:
        """Continuously drain the SDK queue, retaining only the last valid frame."""
        while not self._camera_stop.is_set():
            try:
                if camera.start_video_stream(display=False, resolution=resolution) is False:
                    raise RoboMasterError("camera stream startup rejected by SDK")
                logger.info("RoboMaster camera stream started: resolution=%s strategy=pipeline", resolution)
                last_received = time.monotonic()
                while not self._camera_stop.is_set():
                    try:
                        frame = camera.read_cv2_image(timeout=CAMERA_READ_TIMEOUT_S, strategy="pipeline")
                        if frame is None:
                            raise queue.Empty()
                        if not getattr(frame, "size", 0) or getattr(frame, "ndim", 0) != 3 or frame.shape[2] != 3:
                            raise ValueError("camera returned an invalid BGR frame")
                    except Exception as exc:
                        with self._camera_lock:
                            self._decode_failures += 1
                        if self._camera_stop.is_set():
                            break
                        # A short gap can recover without restarting. A dead SDK
                        # decoder manifests as repeated Empty even when PyAV's
                        # InvalidDataError occurred on its own internal thread.
                        if isinstance(exc, queue.Empty) and time.monotonic() - last_received < CAMERA_RESTART_AFTER_S:
                            continue
                        logger.warning("RoboMaster camera %s; restarting in reader thread: %s",
                                       "invalid video data" if isinstance(exc, InvalidDataError) else type(exc).__name__, exc)
                        break
                    now = time.monotonic()
                    with self._camera_lock:
                        if self._camera_stop.is_set():
                            break
                        self._latest_frame, self._frame_received_at = frame, now
                        self._decode_times.append(now)
                        while self._decode_times and self._decode_times[0] < now - 1.0:
                            self._decode_times.popleft()
                    last_received = now
            except Exception:
                logger.warning("RoboMaster camera startup failed; retrying in reader thread", exc_info=True)
            finally:
                try:
                    camera.stop_video_stream()
                except Exception:
                    logger.warning("RoboMaster camera stream cleanup failed", exc_info=True)
            if self._camera_stop.wait(CAMERA_RESTART_DELAY_S):
                break
            with self._camera_lock:
                self._stream_restarts += 1

    def get_camera_state(self) -> dict:
        """Reader telemetry; timestamps are local monotonic frame-receipt times."""
        now = time.monotonic()
        reader = self._camera_thread
        with self._camera_lock:
            return {
                "last_frame_monotonic_s": self._frame_received_at,
                "frame_age_s": None if self._frame_received_at is None else max(0.0, now - self._frame_received_at),
                "decode_fps": sum(t >= now - 1.0 for t in self._decode_times),
                "decode_failures": self._decode_failures,
                "stream_restarts": self._stream_restarts,
                "reader_alive": reader is not None and reader.is_alive(),
            }

    def get_latest_frame(self, *, max_age_s: float = CAMERA_MAX_FRAME_AGE_S):
        """Immediately copy the latest valid frame, or return None if absent/stale.

        The first request starts the reader asynchronously. SDK I/O never runs here.
        """
        if not math.isfinite(max_age_s) or max_age_s <= 0:
            raise ValueError("max_age_s must be positive and finite")
        if self._ep is None or self._camera_stop.is_set():
            return None
        if self._camera_thread is None:
            self.start_camera()
        with self._camera_lock:
            frame, received_at = self._latest_frame, self._frame_received_at
        logger.info("RoboMaster camera telemetry=%s", self.get_camera_state())
        if received_at is None or time.monotonic() - received_at > max_age_s:
            return None
        return frame.copy()

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
            ep, chassis, sensor, gripper = (
                self._ep, self._chassis, self._sensor, self._gripper,
            )
            camera_thread = self._camera_thread
            self._camera_stop.set()
            self._ep = self._chassis = self._camera = self._sensor = None
            self._robotic_arm = self._gripper = None
        if ep is None:
            return
        self._stop_safely(chassis)
        self._pause_gripper_safely(gripper)
        if camera_thread is not None:
            camera_thread.join(timeout=CAMERA_SHUTDOWN_TIMEOUT_S)
            if camera_thread.is_alive():
                logger.warning("RoboMaster camera reader still stopping; closing SDK connection")
            else:
                self._camera_thread = None
        with self._camera_lock:
            self._latest_frame = self._frame_received_at = None
            self._decode_times.clear()
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
