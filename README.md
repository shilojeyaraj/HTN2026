# htn2026 rover

Autonomous voice-interactive rover built at Hack the North 2026. See [CLAUDE.md](CLAUDE.md) for the full architecture and project context.

## Current milestone: CSI camera → laptop depth → Pi result

Current hardware is a Pi 5, one working CSI camera, and GPS; motors/sensors
are pending. The standalone pipeline below supersedes the older OAK-D/ROS
setup for this milestone. Run commands from the repository root.

### 1. Laptop

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r laptop/requirements.txt
python3 -m laptop.server --host 0.0.0.0
```

The first start downloads [Depth Anything V2 Small](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf).
Wait for `Ready` before starting the client. CPU is the default; use
`--device cuda` or `--device mps` when supported by your PyTorch installation.
Find the laptop's hotspot IP with `hostname -I` on Linux (or Wi-Fi settings).
Both devices must be on the same network. Allow inbound TCP port 8765 if needed.
Use this unauthenticated TCP prototype only on a trusted private network;
the default bind without `--host` is loopback.

### 2. Sync the client from the laptop

```sh
ssh mainuser@172.20.10.11 'mkdir -p ~/HTN2026'
rsync -av pi shared mainuser@172.20.10.11:~/HTN2026/
```

The Pi IP may change; `htn2026.local` may also work. Only `pi/` and `shared/`
are needed on the Pi; there are no pip dependencies there.

### 3. On the Pi

```sh
cd ~/HTN2026
python3 -m pi.client --host LAPTOP_IP --once
# Then repeat continuously, reconnecting after network failures:
python3 -m pi.client --host LAPTOP_IP
```

Each request captures a fresh 640×480 JPEG using `rpicam-still`, sends it,
and waits for a JSON reply before capturing again (no frame backlog).
`--timeout 30` sets network wait time; increase it if CPU inference is slower.
`--interval 0.2` sets the pause between completed rounds. Capture itself has
a 10-second timeout. Camera startup per frame limits throughput initially.

Replies contain `relative_proximity` for left/center/right (0 = relatively
farther, 1 = relatively nearer), raw inverse-depth scores, a
`preferred_direction`, and timing. Scores use the 90th percentile of each
third of the middle half of the image, normalized against that frame's
5th/95th percentiles. These are **not meters, clearance, or calibrated
collision probabilities**, and scores are not comparable across frames.
Flat maps return `uncertain`; failed inference returns `error`.
The preferred direction only identifies the relatively farther region.

This milestone only prints results. It does not connect to the existing
arbiter or motors. Before movement, add independent onboard obstacle sensing
and a motor watchdog that stops on stale commands (~0.5 seconds); laptop
depth over Wi-Fi cannot provide the existing onboard safety guarantee.

### Local checks without the Pi

```sh
python3 -m unittest test_camera_pipeline
# With the real server running, use any local JPEG to test actual inference:
python3 -m pi.client --host 127.0.0.1 --image /path/to/photo.jpg --once
```

The automated check covers fragmented TCP messages, length limits,
disconnects, invalid JPEG recovery, and depth reduction with synthetic data.
It does not download model weights or verify physical camera capture.
Wire format: 4-byte unsigned big-endian length + JPEG request / UTF-8 JSON
reply, maximum 2 MiB / 8 KiB respectively. One request is in flight at a time.

## Earlier full-stack scaffold (camera integration unfinished)

### Setup

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in real keys, never commit .env
```

### Running

```
python3 -m control.reflex   # fast reflex loop only
python3 -m brain.graph      # deliberative agent loop only
python3 main.py             # full stack
```
