"""WebSocket server that streams the occupancy map to the frontend at ~5 Hz.

Runs on the Pi (or laptop) alongside the main stack. The frontend connects and
renders the map on a canvas. Uses the `websockets` library (pip install websockets).

Usage:
    server = MapServer(mapper, get_pose, brain_activity, sensor_state, insights)
    server.run_forever(host="0.0.0.0", port=8766)

Frontend connects to: ws://<pi-ip>:8766/map
"""

import asyncio
import json
import logging
import threading

import websockets

STREAM_HZ = 5


class MapServer:
    def __init__(self, mapper=None, get_pose=None, brain_activity=None, sensor_state=None, insights=None,
                 *, get_snapshot=None):
        self.mapper = mapper
        self.get_pose = get_pose
        self.brain_activity = brain_activity
        self.sensor_state = sensor_state
        self.insights = insights
        self.get_snapshot = get_snapshot
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread = None
        self._error = None
        self.port = None

    def _payload(self):
        if self.get_snapshot is not None:
            return self.get_snapshot()
        payload = self.mapper.to_payload(self.get_pose())
        if self.brain_activity is not None:
            payload["brain_activity"] = self.brain_activity.recent(10)
        if self.sensor_state is not None:
            payload["sensor_state"] = self.sensor_state.snapshot()
        if self.insights is not None:
            payload["insights"] = self.insights.get()
        return payload

    async def _handler(self, websocket):
        period = 1.0 / STREAM_HZ
        try:
            while not self._stop.is_set():
                await websocket.send(json.dumps(self._payload(), default=str, allow_nan=False))
                await asyncio.sleep(period)
        except websockets.exceptions.ConnectionClosed:
            pass

    async def _run(self, host: str, port: int):
        async with websockets.serve(self._handler, host, port, close_timeout=1) as server:
            self.port = server.sockets[0].getsockname()[1]
            self._ready.set()
            logging.getLogger(__name__).info("Dashboard telemetry listening on %s:%s", host, self.port)
            while not self._stop.is_set():
                await asyncio.sleep(0.1)
            # Deliver the terminal mission state before closing connected dashboards.
            websockets.broadcast(server.connections, json.dumps(self._payload(), default=str, allow_nan=False))

    def run_forever(self, host: str = "0.0.0.0", port: int = 8766) -> None:
        asyncio.run(self._run(host, port))

    def start(self, host="0.0.0.0", port=8766):
        """Own a separate event loop so synchronous SDK moves cannot freeze the UI."""
        def run():
            try:
                self.run_forever(host, port)
            except Exception as exc:
                self._error = exc
                self._ready.set()
                logging.getLogger(__name__).exception("Dashboard telemetry server failed")
        self._thread = threading.Thread(target=run, name="dashboard-telemetry", daemon=True)
        self._thread.start()
        if not self._ready.wait(5):
            self.close()
            raise TimeoutError("Dashboard telemetry server did not start")
        if self._error is not None:
            raise self._error

    def close(self):
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
