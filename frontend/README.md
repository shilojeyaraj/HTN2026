# Rover dashboard

React / TypeScript / Vite dashboard for the RoboMaster runtime. Dashboard, Telemetry,
and Brain use one shared, read-only WebSocket feed. Encounters remains explicitly
labelled sample data.

## Launch

From the repository root, with the Python requirements installed and the laptop on
the RoboMaster's STA network:

```sh
python main.py
```

This connects to the rover and monitors telemetry without issuing movement commands.
Cloud credentials are not required for monitoring. Camera capture starts only when
an autonomous mission needs it. Ctrl+C shuts down the server and robot connection,
including the controller's normal stop/pause cleanup.

In a second terminal:

```sh
cd frontend
npm ci
npm run dev
```

Open the Vite URL, normally http://localhost:5173. To monitor a mission, run
`python main.py --goal "your mission"` instead of the monitoring process. Use a single
runtime process/robot connection. When a mission finishes, the server sends its final
snapshot and exits; the UI retains the last snapshot and marks the feed offline.

The runtime binds port 8766 by default. Stop the old `mock_map_server.py` before
starting it, or select `--telemetry-port 8767`. The old mock map packets are not live
rover telemetry and are rejected by this dashboard.

## Different hosts or ports

The browser connects to `ws://<page-hostname>:8766` by default (`wss://` on HTTPS).
If Python runs elsewhere, create `frontend/.env.local`:

```dotenv
VITE_TELEMETRY_URL=ws://192.168.1.20:8766
```

Restart Vite after changing this value. For LAN access, run
`npm run dev -- --host 0.0.0.0` and open the laptop's IP. The Python bind address is
configurable with `--telemetry-host`. HTTPS hosting needs a reverse proxy that
terminates TLS for the WebSocket; the Python server itself uses plain WebSocket.
Do not put provider or MongoDB credentials in frontend environment variables.

## What is live

- Position/trail, yaw/pitch/roll, body-frame forward/sideways velocity, chassis flags,
  raw ToF channels, and battery percentage when SDK subscriptions supply them.
- Per-source subscription state, receipt timestamp, and age. Readings become stale
  after 2 seconds; unavailable readings stay empty. Browser feed freshness expires
  after 2.5 seconds without a valid message.
- Camera frame age, decoded FPS, decode failures, and restarts.
- Mission mode/phase/reason, observations, findings, retry state, inference time,
  and the last 40 actions, including requested/applied arguments and errors.
- The last 30 chassis alerts and stop request outcome. Stationary/moving is reported
  only from a fresh chassis-status sample received after the stop request. Speech
  actions are marked queued because playback completion is not observed.

The publisher runs on its own thread and event loop, so an SDK movement waiting for
completion does not freeze dashboard updates. Snapshots contain no API keys.

GPS, ambient temperature, microphone/depth, wheel encoders, and arm/gripper feedback
are not connected. The track shows SDK position estimates; it is not an occupancy
map. ToF sensor directions are not inferred. No automatic obstacle reflex or browser
robot-control commands are added by this telemetry feed.

## Checks

```sh
npm run build
npm run lint
```

From the repository root:

```sh
python -m pytest -q -m 'not integration' tests
```

Tests use fake hardware and include a real loopback WebSocket test that verifies
snapshots keep arriving during a blocked motor action. No physical rover movement
is required.
