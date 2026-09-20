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

import websockets

STREAM_HZ = 5


class MapServer:
    def __init__(self, mapper, get_pose, brain_activity=None, sensor_state=None, insights=None):
        self.mapper = mapper
        self.get_pose = get_pose
        self.brain_activity = brain_activity
        self.sensor_state = sensor_state
        self.insights = insights

    async def _handler(self, websocket):
        period = 1.0 / STREAM_HZ
        while True:
            payload = self.mapper.to_payload(self.get_pose())
            if self.brain_activity is not None:
                payload["brain_activity"] = self.brain_activity.recent(10)
            if self.sensor_state is not None:
                payload["sensor_state"] = self.sensor_state.snapshot()
            if self.insights is not None:
                payload["insights"] = self.insights.get()
            await websocket.send(json.dumps(payload, default=str))
            await asyncio.sleep(period)

    async def _run(self, host: str, port: int):
        async with websockets.serve(self._handler, host, port):
            await asyncio.Future()

    def run_forever(self, host: str = "0.0.0.0", port: int = 8766) -> None:
        asyncio.run(self._run(host, port))
