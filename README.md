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

For this laptop's existing `venv` and downloaded test cache:

```sh
HF_HOME=/tmp/htn2026-hf venv/bin/python -m laptop.server --host 0.0.0.0
```

Use a writable `HF_HOME` if your environment points to `/opt/hf-cache`.

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
# Then stream continuously, reconnecting after network failures:
python3 -m pi.client --host LAPTOP_IP --fps 15 --quality 70
```

Replace `LAPTOP_IP` with the laptop's actual hotspot address (last verified:
`172.20.10.3`), never `0.0.0.0` or the Pi's address.

One persistent [`rpicam-vid` process](https://www.raspberrypi.com/documentation/computers/camera_software.html#rpicam-vid)
captures 640×480 MJPEG into a pipe at a target 15 FPS. Frames are sent over
TCP while a separate thread receives depth results. The laptop displays
incoming frames immediately and runs depth on the newest available frame;
it drops older pending frames instead of queuing inference work. The Pi
also keeps only its newest pending capture if transmission falls behind.
TCP itself can still add delay on congested Wi-Fi; reduce `--fps` or
`--quality` if needed. Actual preview FPS depends on the camera, Wi-Fi,
and laptop load; 15 FPS is a target, not a measured hardware guarantee.
`--timeout 30` limits camera inactivity and network waits, including gaps
between depth results. Increase it if inference takes longer than 30 seconds.
`--fps` replaces the old `--interval` flag. `--once` still sends one frame
and waits for its depth result.

The laptop opens a live preview window when the first valid frame arrives.
Run the server from your laptop desktop session; Tkinter and Pillow display
the incoming frames entirely in memory. No frames are saved on either device;
previous captures in `test/` are left alone. Close the window or press Escape
to stop the server. Use `--no-preview` for a headless session. Tkinter is
included in many Python installations (on Ubuntu/Debian, install `python3-tk`
if missing; custom Python builds also need Tk support).
For this streaming upgrade, re-run the sync step from your laptop and restart
both server and Pi client. The desktop window remains responsive during depth
inference. Stopping the Pi client also terminates its camera subprocess.

The window title reports displayed FPS. To isolate CPU inference from camera,
Wi-Fi, and display performance, restart the laptop server with `--no-depth`:

```sh
venv/bin/python -m laptop.server --host 0.0.0.0 --no-depth
```

This mode skips model loading entirely and returns `status: "preview"` with
no depth estimates. Re-sync the client before using it. Compare displayed FPS
with and without depth enabled: an improvement implicates inference overhead;
otherwise investigate capture/network/display or stale processes first.

Replies contain `relative_proximity` for left/center/right (0 = relatively
farther, 1 = relatively nearer), raw inverse-depth scores, a
`preferred_direction`, and timing. Scores use the 90th percentile of each
third of the middle half of the image, normalized against that frame's
5th/95th percentiles. These are **not meters, clearance, or calibrated
collision probabilities**, and scores are not comparable across frames.
Flat maps return `uncertain`; failed inference returns `error`.
The preferred direction only identifies the relatively farther region.

`frame_id` identifies the sampled frame's position in this TCP connection,
starting at 1; gaps are expected because depth samples fewer frames than the
preview displays. `processing_ms` measures depth processing time;
`server_frame_age_ms` measures time from full frame receipt to result creation
on the laptop. It excludes Pi capture and network transit. The old
`capture_roundtrip_ms` field is removed because capture and replies now overlap.

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

The automated check covers fragmented TCP/MJPEG messages, length limits,
disconnects, invalid JPEG recovery, camera-process cleanup, depth reduction,
and preview delivery plus frame dropping while synthetic inference is blocked.
It does not download model weights or verify physical camera capture.
Wire format: 4-byte unsigned big-endian length + JPEG upstream / UTF-8 JSON
downstream, maximum 2 MiB / 8 KiB respectively. Directions are independent;
only frames sampled by depth produce replies. JPEG/JSON framing is unchanged.

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
