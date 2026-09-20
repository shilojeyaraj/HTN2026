"""Real dashboard payloads with fake hardware; no cloud services or robot movement."""

import asyncio
import json
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from websockets.sync.client import connect

from brain import loop
from brain.state import RobotState
from control.map_server import MapServer
from control.robomaster import RoboMasterError, TELEMETRY_MAX_AGE_S
from control.telemetry import rover_snapshot
from tests.test_multimodal_loop import decision, setup_loop
from tests.test_robomaster_controller import EP, make_controller


def test_sources_battery_freshness_validation_and_reconnect(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr('control.robomaster.time.monotonic', lambda: clock[0])
    ep = EP()
    ep.battery = SimpleNamespace(sub_battery_info=lambda **kw: setattr(ep, 'battery_callback', kw['callback']),
                                 unsub_battery_info=MagicMock())
    controller = make_controller(ep).connect()
    try:
        initial = controller.get_telemetry()
        assert not initial['connected']
        assert all(s['status'] == 'unavailable' for s in initial['sources'].values())
        assert initial['sources']['battery_percent']['subscription'] == 'active'
        ep.battery_callback(63)
        ep.chassis.subscriptions['sub_position']((1, 2, 0))
        data = controller.get_telemetry()
        assert data['connected'] and data['sources']['battery_percent']['value'] == 63
        assert data['trail'] == [[1, 2]]
        clock[0] += TELEMETRY_MAX_AGE_S + 0.1
        assert not controller.get_telemetry()['connected']
        assert controller.get_telemetry()['sources']['position_m']['status'] == 'stale'
        ep.battery_callback(float('nan'))
        assert controller.get_telemetry()['sources']['battery_percent']['value'] is None
        json.dumps(rover_snapshot(controller, RobotState()), allow_nan=False)
        controller.close()
        ep.battery.unsub_battery_info.assert_called_once()
        controller.connect()
        assert controller.get_chassis_state() == {}
        assert controller.get_telemetry()['trail'] == []
    finally:
        controller.close()


def test_failed_and_unsupported_subscriptions_are_visible():
    ep = EP()
    ep.chassis.sub_position = lambda **_: False
    controller = make_controller(ep).connect()
    try:
        sources = controller.get_telemetry()['sources']
        assert sources['position_m']['subscription'] == 'failed'
        assert sources['battery_percent']['subscription'] == 'unsupported'
    finally:
        controller.close()


def test_alerts_are_latched_and_stop_requires_a_fresh_post_request_sample():
    ep = EP()
    controller = make_controller(ep).connect()
    try:
        status = ep.chassis.subscriptions['sub_status']
        status([1, 0, 0, 0, 0, 1, 1, 0, 0, 0, 0])
        controller.stop()
        assert controller.get_telemetry()['stop']['motion'] == 'unknown'
        status([1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0])
        telemetry = controller.get_telemetry()
        assert telemetry['stop']['status'] == 'accepted'
        assert telemetry['stop']['motion'] == 'stationary'
        assert {a['name'] for a in telemetry['alerts']} == {'slipping', 'impact_x'}
        controller._received_at['status'] -= TELEMETRY_MAX_AGE_S + 1
        assert controller.get_telemetry()['stop']['motion'] == 'unknown'
        ep.chassis.drive_speed = lambda **_: False
        with pytest.raises(RoboMasterError):
            controller.stop()
        assert controller.get_telemetry()['stop']['status'] == 'failed'
    finally:
        controller.close()


def test_action_rejection_and_direct_failure_are_not_reported_as_success():
    ep = EP()
    controller = make_controller(ep).connect()
    state = RobotState(current_goal='forward 1 meter')
    try:
        loop._execute_verb('forward', {'distance_m': 'invalid'}, state, controller)
        rejected = state.telemetry.snapshot()['actions'][-1]
        assert rejected['status'] == 'rejected' and rejected['duration_ms'] >= 0
        assert not ep.chassis.moves
        ep.chassis.next_action.error = RuntimeError('motor fault')
        asyncio.run(loop.run_episode(state, controller))
        mission = state.telemetry.snapshot()
        assert mission['phase'] == 'failed'
        assert [a['status'] for a in mission['actions']] == ['rejected', 'error', 'completed']
        assert mission['actions'][1]['applied_args'] == {'distance_m': 0.75}
        assert controller.get_telemetry()['stop']['status'] == 'accepted'
    finally:
        controller.close()


def test_mission_wait_retry_and_completion_states(setup_loop):
    controller, camera, model, _ = setup_loop
    state = RobotState(current_goal='find the red chair')
    async def run():
        camera.return_value = None
        await loop.run_episode(state, controller)
        assert state.telemetry.snapshot()['phase'] == 'waiting_camera'
        camera.return_value = b'jpeg'
        state.retry_at = 0
        model.return_value = 'malformed'
        await loop.run_episode(state, controller)
        assert state.telemetry.snapshot()['phase'] == 'retrying'
        state.retry_at = 0
        model.return_value = decision(None, {}, goal_complete=True)
        await loop.run_episode(state, controller)
        mission = state.telemetry.snapshot()
        assert mission['phase'] == 'complete' and mission['scene_at'] is not None
        assert mission['inference_ms'] >= 0
    asyncio.run(run())


def test_websocket_keeps_streaming_during_blocking_action_and_sends_terminal_state():
    ep = EP()
    controller = make_controller(ep).connect()
    state = RobotState(current_goal='forward 0.2 meters')
    entered, release = threading.Event(), threading.Event()
    def wait():
        entered.set()
        assert release.wait(4)
        return True
    ep.chassis.next_action.wait_for_completed = wait
    server = MapServer(get_snapshot=lambda: rover_snapshot(controller, state))
    server.start('127.0.0.1', 0)
    worker = threading.Thread(target=lambda: asyncio.run(loop.run_episode(state, controller)))
    try:
        with connect(f'ws://127.0.0.1:{server.port}', proxy=None) as ws:
            first = json.loads(ws.recv(timeout=2))
            assert first['schema'] == 'rover.v1'
            worker.start()
            assert entered.wait(1)
            while True:
                active = json.loads(ws.recv(timeout=2))
                if active['mission']['actions']:
                    break
            assert active['mission']['actions'][-1]['status'] == 'executing'
            ep.chassis.subscriptions['sub_position']((0.1, 0, 0))
            next_frame = json.loads(ws.recv(timeout=2))
            assert next_frame['timestamp'] > active['timestamp']
            assert next_frame['rover']['sources']['position_m']['value'] == [0.1, 0, 0]
            assert worker.is_alive()
            release.set()
            worker.join(2)
            server.close()
            messages = [json.loads(message) for message in ws]
            assert messages[-1]['mission']['phase'] == 'complete'
            action = messages[-1]['mission']['actions'][-1]
            assert action['status'] == 'completed' and action['applied_args'] == {'distance_m': 0.2}
    finally:
        release.set()
        if worker.ident is not None:
            worker.join(2)
        server.close()
        controller.close()
    assert not server._thread.is_alive()


@pytest.mark.parametrize("startup_scan", [False, True])
def test_monitor_mode_scans_once_when_enabled_then_starts_monitoring(startup_scan, monkeypatch):
    import main
    controller, server = MagicMock(), MagicMock()
    monkeypatch.setattr(main, 'RoboMasterController', lambda: controller)
    monkeypatch.setattr(main, 'MapServer', lambda **_: server)
    monkeypatch.setattr(main, 'STARTUP_SCAN_ENABLED', startup_scan)
    async def complete_scan(state, _controller):
        assert state.current_goal is None and state.startup_scan_status == 'pending'
        state.startup_scan_status = 'completed'
        return state
    episode = AsyncMock(side_effect=complete_scan)
    monkeypatch.setattr(main, 'run_episode', episode)
    monkeypatch.setattr(main, 'brain', SimpleNamespace(aclose=AsyncMock()))
    monkeypatch.setattr(main, 'aclose_vision_client', AsyncMock())
    monkeypatch.setattr('sys.argv', ['main.py'])
    monkeypatch.setattr(main.asyncio, 'sleep', AsyncMock(side_effect=asyncio.CancelledError))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(main.main())
    server.start.assert_called_once_with('0.0.0.0', 8766)
    server.close.assert_called_once()
    controller.__exit__.assert_called_once()
    assert episode.await_count == int(startup_scan)


def test_monitor_entrypoint_loads_without_cloud_credentials():
    import os
    import subprocess
    import sys
    env = {key: value for key, value in os.environ.items()
           if key not in {'ELEVENLABS_API_KEY', 'VOICE_ID', 'BACKBOARD_API_KEY', 'GEMINI_API_KEY'}}
    env['PYTHON_DOTENV_DISABLED'] = '1'
    result = subprocess.run([sys.executable, 'main.py', '--help'], env=env,
                            capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    assert 'omit to scan once, then monitor' in ' '.join(result.stdout.split())
