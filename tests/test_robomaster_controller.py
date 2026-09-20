import queue
from types import SimpleNamespace

import pytest

from control.robomaster import RoboMasterController, RoboMasterError


class Action:
    def __init__(self, error=None):
        self.error = error

    def wait_for_completed(self):
        if self.error:
            raise self.error


class Chassis:
    def __init__(self):
        self.moves = []
        self.stops = []
        self.subscriptions = {}
        self.next_action = Action()

    def move(self, **kwargs):
        self.moves.append(kwargs)
        return self.next_action

    def drive_speed(self, **kwargs):
        self.stops.append(kwargs)

    def __getattr__(self, name):
        if name.startswith("sub_"):
            return lambda freq, callback: self.subscriptions.__setitem__(name, callback)
        if name.startswith("unsub_"):
            return lambda: None
        raise AttributeError(name)


class Camera:
    def __init__(self, frames=()):
        self.frames = list(frames)
        self.started = []
        self.stopped = False

    def start_video_stream(self, **kwargs):
        self.started.append(kwargs)

    def read_cv2_image(self, **_kwargs):
        item = self.frames.pop(0) if self.frames else None
        if isinstance(item, Exception):
            raise item
        return item

    def stop_video_stream(self):
        self.stopped = True


class EP:
    def __init__(self, frames=()):
        self.chassis = Chassis()
        self.camera = Camera(frames)
        self.sensor = SimpleNamespace(
            sub_distance=lambda freq, callback: setattr(self, "tof_callback", callback),
            unsub_distance=lambda: None,
        )
        self.initialize_calls = []
        self.closed = False

    def initialize(self, **kwargs):
        self.initialize_calls.append(kwargs)
        return True

    def close(self):
        self.closed = True


def make_controller(ep):
    return RoboMasterController(
        robot_factory=lambda: ep,
        camera_module=SimpleNamespace(STREAM_360P="360p"),
        sleep=lambda _seconds: None,
    )


def test_connects_once_with_ap_and_exposes_real_chassis():
    ep = EP()
    controller = make_controller(ep)

    assert controller.connect() is controller
    assert controller.connect() is controller
    assert ep.initialize_calls == [{"conn_type": "ap"}]
    assert controller.chassis is ep.chassis
    assert controller.camera is ep.camera


def test_discrete_movements_use_chassis_move_with_expected_coordinates():
    ep = EP()
    controller = make_controller(ep).connect()

    assert controller.forward(0.5) == {"status": "completed"}
    assert controller.backward(0.5) == {"status": "completed"}
    assert controller.strafe_left(0.2) == {"status": "completed"}
    assert controller.strafe_right(0.2) == {"status": "completed"}
    assert controller.turn(-30) == {"status": "completed"}

    assert ep.chassis.moves == [
        {"x": 0.5, "y": 0, "z": 0, "xy_speed": 0.5, "z_speed": 30.0},
        {"x": -0.5, "y": 0, "z": 0, "xy_speed": 0.5, "z_speed": 30.0},
        {"x": 0, "y": 0.2, "z": 0, "xy_speed": 0.5, "z_speed": 30.0},
        {"x": 0, "y": -0.2, "z": 0, "xy_speed": 0.5, "z_speed": 30.0},
        {"x": 0, "y": 0, "z": -30, "xy_speed": 0.5, "z_speed": 30.0},
    ]


def test_failed_move_requests_stop_before_raising():
    ep = EP()
    ep.chassis.next_action = Action(RuntimeError("link lost"))
    controller = make_controller(ep).connect()

    with pytest.raises(RoboMasterError, match="movement failed"):
        controller.forward(0.2)

    assert ep.chassis.stops[-1] == {"x": 0, "y": 0, "z": 0}


def test_camera_retries_queue_empty_then_returns_newest_frame_and_closes():
    frame = object()
    ep = EP(frames=[queue.Empty(), None, frame])
    controller = make_controller(ep).connect()

    assert controller.get_latest_frame() is frame
    assert ep.camera.started == [{"display": False, "resolution": "360p"}]

    assert controller.get_latest_frame(retries=1) is None
    assert len(ep.camera.started) == 1

    controller.close()
    assert ep.camera.stopped
    assert ep.closed


def test_camera_falls_back_for_sdk_versions_without_a_resolution_argument():
    class OldCamera(Camera):
        def start_video_stream(self, *, display):
            self.started.append({"display": display})

    ep = EP()
    ep.camera = OldCamera(["frame"])
    controller = make_controller(ep).connect()

    assert controller.get_latest_frame() == "frame"
    assert ep.camera.started == [{"display": False}]


def test_camera_start_failure_returns_none_without_retrying_startup():
    class BrokenCamera(Camera):
        def start_video_stream(self, **_kwargs):
            self.started.append({"attempted": True})
            raise RuntimeError("stream unavailable")

    ep = EP()
    ep.camera = BrokenCamera([])
    controller = make_controller(ep).connect()

    assert controller.get_latest_frame() is None
    assert controller.get_latest_frame() is None
    assert ep.camera.started == [{"attempted": True}]


def test_telemetry_is_only_reported_after_sdk_callbacks_arrive():
    ep = EP()
    controller = make_controller(ep).connect()

    assert controller.get_chassis_state() == {}
    ep.chassis.subscriptions["sub_position"]((1.0, 2.0, 3.0))
    ep.chassis.subscriptions["sub_attitude"]((4.0, 5.0, 6.0))
    ep.tof_callback([100, 200, 300, 400])

    assert controller.get_chassis_state() == {
        "position_m": (1.0, 2.0, 3.0),
        "attitude_deg": (4.0, 5.0, 6.0),
    }
    assert controller.get_tof_distances() == {"tof_mm": (100, 200, 300, 400)}
