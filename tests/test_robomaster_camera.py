"""No robot/network: exercise the actual reader thread with a blocking SDK fake."""

import asyncio
import queue
import threading
import time
from unittest.mock import AsyncMock, Mock

import numpy as np
import pytest
from av.error import InvalidDataError

from control import robomaster
from tests.test_robomaster_controller import EP, make_controller


class StreamingCamera:
    def __init__(self):
        self.frames = queue.Queue()
        self.started = []
        self.reads = []
        self.stops = []
        self.start_gate = threading.Event()
        self.start_gate.set()
        self.entered_start = threading.Event()
        self.fail_start = False

    def start_video_stream(self, **kwargs):
        self.started.append((kwargs, threading.get_ident()))
        self.entered_start.set()
        assert self.start_gate.wait(2), "test must release blocked startup"
        return not self.fail_start

    def read_cv2_image(self, **kwargs):
        self.reads.append((kwargs, threading.get_ident()))
        frame = self.frames.get(timeout=kwargs["timeout"])
        if isinstance(frame, Exception):
            raise frame
        return frame

    def stop_video_stream(self):
        self.stops.append(threading.get_ident())
        return True


def wait_until(predicate):
    deadline = time.monotonic() + 2
    while not predicate():
        assert time.monotonic() < deadline, "reader did not reach expected state"
        time.sleep(0.005)


@pytest.fixture
def stream(monkeypatch):
    monkeypatch.setattr(robomaster, "CAMERA_READ_TIMEOUT_S", 0.02)
    ep = EP()
    ep.camera = StreamingCamera()
    controller = make_controller(ep).connect()
    try:
        yield controller, ep.camera, ep
    finally:
        ep.camera.start_gate.set()
        controller.close()


def publish(controller, camera, value):
    frame = np.full((8, 8, 3), value, dtype=np.uint8)
    camera.frames.put(frame)
    wait_until(lambda: controller._latest_frame is frame)
    return frame


def test_getter_never_waits_for_sdk_startup_or_read_and_reader_starts_once(stream):
    controller, camera, ep = stream
    camera.start_gate.clear()
    started = time.perf_counter()
    assert controller.get_latest_frame() is None
    assert time.perf_counter() - started < 0.1
    assert camera.entered_start.wait(1)
    worker = controller._camera_thread
    for _ in range(5):
        controller.start_camera()
        assert controller.get_latest_frame() is None
    assert controller._camera_thread is worker
    camera.start_gate.set()
    publish(controller, camera, 1)
    latest = publish(controller, camera, 2)

    started = time.perf_counter()
    for _ in range(100):
        frame = controller.get_latest_frame()
        assert np.array_equal(frame, latest)
    assert time.perf_counter() - started < 0.1
    frame[:] = 99
    assert np.array_equal(controller.get_latest_frame(), latest)  # Consumer owns its copy.
    assert len(camera.started) == 1
    assert camera.started[0][0] == {"display": False, "resolution": "360p"}
    assert all(kwargs == {"timeout": 0.02, "strategy": "pipeline"} for kwargs, _ in camera.reads)
    assert all(tid == worker.ident for _, tid in camera.started + camera.reads)
    assert worker.ident != threading.get_ident()
    stats = controller.get_camera_state()
    assert stats["frame_age_s"] < 0.2 and stats["decode_fps"] == 2
    assert stats["last_frame_monotonic_s"] is not None
    assert stats["stream_restarts"] == 0

    controller.close()
    assert not worker.is_alive()
    assert camera.stops == [worker.ident]
    assert ep.closed and controller.get_latest_frame() is None


def test_brief_empty_read_keeps_latest_good_frame_without_restart(stream):
    controller, camera, _ = stream
    controller.start_camera()
    frame = publish(controller, camera, 7)
    received_at = controller.get_camera_state()["last_frame_monotonic_s"]
    camera.frames.put(queue.Empty())
    wait_until(lambda: controller.get_camera_state()["decode_failures"] > 0)
    assert np.array_equal(controller.get_latest_frame(), frame)
    assert controller.get_camera_state()["last_frame_monotonic_s"] == received_at
    assert controller.get_camera_state()["stream_restarts"] == 0


@pytest.mark.parametrize("failure", [InvalidDataError(1, "bad video"), queue.Empty(), np.zeros((0, 0, 3), dtype=np.uint8)])
def test_reader_recovers_without_discarding_good_frame_or_blocking_getter(failure, stream, monkeypatch):
    controller, camera, _ = stream
    monkeypatch.setattr(robomaster, "CAMERA_RESTART_AFTER_S", 0.05)
    monkeypatch.setattr(robomaster, "CAMERA_RESTART_DELAY_S", 0.01)
    controller.start_camera()
    old = publish(controller, camera, 3)
    received_at = controller.get_camera_state()["last_frame_monotonic_s"]
    camera.start_gate.clear()  # The restart itself can block; perception must not.
    camera.frames.put(failure)
    wait_until(lambda: len(camera.started) == 2)
    started = time.perf_counter()
    assert np.array_equal(controller.get_latest_frame(), old)
    assert time.perf_counter() - started < 0.1
    stats = controller.get_camera_state()
    assert stats["last_frame_monotonic_s"] == received_at
    assert stats["stream_restarts"] == 1 and stats["decode_failures"] > 0
    camera.start_gate.set()
    new = publish(controller, camera, 4)
    assert np.array_equal(controller.get_latest_frame(), new)


@pytest.mark.parametrize("stale", [False, True])
def test_missing_or_stale_frame_blocks_autonomous_planning_and_motion(stale, stream, monkeypatch):
    from brain import loop
    from brain.state import RobotState

    controller, camera, ep = stream
    controller.start_camera()
    if stale:
        good = publish(controller, camera, 5)
        with controller._camera_lock:
            controller._frame_received_at -= robomaster.CAMERA_MAX_FRAME_AGE_S + 1
        assert controller.get_latest_frame() is None
        assert controller._latest_frame is good  # Rejection doesn't clear the buffer.
    vision = AsyncMock(side_effect=AssertionError("unsafe frame must not reach vision"))
    planner = AsyncMock(side_effect=AssertionError("unsafe frame must not reach planner"))
    monkeypatch.setattr(loop, "decide_action", vision)
    monkeypatch.setattr(loop.brain, "run_tools", planner)
    state = asyncio.run(loop.run_episode(RobotState(current_goal="find the chair", scene_fresh=True), controller))
    assert not state.scene_fresh
    vision.assert_not_called()
    planner.assert_not_awaited()
    assert ep.chassis.moves == []


def test_failed_start_is_retried_in_reader_and_shutdown_is_idempotent(stream, monkeypatch):
    controller, camera, ep = stream
    monkeypatch.setattr(robomaster, "CAMERA_RESTART_DELAY_S", 0.01)
    camera.fail_start = True
    assert controller.get_latest_frame() is None
    wait_until(lambda: controller.get_camera_state()["stream_restarts"] >= 1)
    camera.fail_start = False
    publish(controller, camera, 8)
    worker = controller._camera_thread
    controller.close()
    stopped = len(camera.stops)
    controller.close()
    assert len(camera.stops) == stopped and not worker.is_alive()
    assert ep.closed


def test_shutdown_without_camera_use_never_starts_video(stream):
    controller, camera, _ = stream
    controller.close()
    assert camera.started == camera.reads == camera.stops == []


def test_reconnect_starts_one_new_reader_and_cannot_reuse_previous_frame(stream):
    controller, camera, _ = stream
    controller.start_camera()
    publish(controller, camera, 9)
    old_worker = controller._camera_thread
    controller.close()
    assert not old_worker.is_alive()
    controller.connect()
    assert controller.get_latest_frame() is None
    assert controller._camera_thread is not old_worker
    publish(controller, camera, 10)
    assert len(camera.started) == 2
