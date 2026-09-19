# htn2026 rover

Autonomous voice-interactive rover built at Hack the North 2026. See [CLAUDE.md](CLAUDE.md) for the full architecture and project context.

## Current milestone: USB webcam + microphone → laptop

A USB webcam plugs into the Pi 5. Its video and microphone audio stream to
one laptop over TCP. The laptop opens a live video window and plays microphone
audio through its normal output device. Optional monocular depth runs independently.
Nothing is recorded to disk. Run commands from the repository root.

### 1. Laptop

FFmpeg/ffplay must be installed for live audio (`sudo apt install ffmpeg` on
Debian/Ubuntu). This laptop already has them. Python setup:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r laptop/requirements.txt
python3 -m laptop.server --host 0.0.0.0 --no-depth
```

For this laptop's existing environment, the equivalent command is:

```sh
venv/bin/python -m laptop.server --host 0.0.0.0 --no-depth
```

Wait for `Ready` before starting the Pi. `--no-depth` skips the model entirely;
remove it to enable [Depth Anything V2 Small](https://huggingface.co/depth-anything/Depth-Anything-V2-Small-hf).
If the model cache points to unwritable `/opt/hf-cache`, prefix the command
with `HF_HOME=/tmp/htn2026-hf` to use the existing downloaded test cache.
CPU is the default; `--device cuda` / `--device mps` select supported accelerators.
`--mute` receives audio without playing it. `--no-preview` hides video but does
not mute audio. Tkinter/Pillow provide the desktop preview; Python needs Tk
support (`python3-tk` on Debian/Ubuntu, or Tk support in a custom Python build).

Both devices must be on the same network. Allow inbound TCP port 8765 if
needed. This prototype is unauthenticated; use a trusted private network.
Without `--host`, the server binds only to localhost.

### 2. Sync from the laptop

```sh
ssh mainuser@172.20.10.11 'mkdir -p ~/HTN2026'
rsync -av pi shared mainuser@172.20.10.11:~/HTN2026/
```

Re-sync and restart both processes for this webcam/audio upgrade. The Pi IP
may change; `htn2026.local` may also work. Only `pi/` and `shared/` are needed
on the Pi; there are no Python package dependencies there.

### 3. Find the webcam and microphone on the Pi

```sh
sudo apt update
sudo apt install ffmpeg v4l-utils alsa-utils
v4l2-ctl --list-devices
v4l2-ctl --device /dev/video0 --list-formats-ext
arecord -l
```

Select the webcam's **capture** device (some webcams expose multiple video
nodes). Select its audio card from `arecord -l`; audio and video device numbers
are independent. A webcam without a built-in mic needs a separate USB mic.

### 4. Start on the Pi

For example, **if** the webcam is `/dev/video0` and its microphone is ALSA
card 1, device 0:

```sh
cd ~/HTN2026
python3 -m pi.client --host 172.20.10.3 --video-device /dev/video0 --audio-device plughw:1,0 --fps 15
```

Replace these device names and the laptop IP with the actual values.
`172.20.10.3` was the last verified laptop hotspot address; find the current
one on the laptop with `ip -4 route`. Do not use `0.0.0.0` as the Pi's target.

Defaults are `/dev/video0` for video and ALSA `default` for the microphone.
Explicit `--audio-device` is preferable because the default may select a
different input. `plughw` allows ALSA to convert device formats when needed.

The default requests webcam-native MJPEG at 640×480 and 15 FPS. We copy its
JPEG frames without re-encoding on the Pi. Check the webcam's supported modes:
if it does not offer MJPEG, try `--input-format yuyv422`. That fallback encodes
JPEG on the Pi and uses more CPU. `--width`, `--height`, and `--fps` must match
an available camera mode (dimensions are limited to 1920 per side).
`--quality 70` controls JPEG quality only in the raw-video fallback; it does
not alter webcam-native MJPEG. Reduce resolution/FPS if Wi-Fi cannot keep up.

Use `--no-audio` on the Pi for video-only capture. `--once` sends one video
frame and waits for its result, with audio disabled. `--image photo.jpg`
remains a webcam-free video test and also disables audio. Camera and microphone
errors are printed by FFmpeg; check the device arguments if either fails.
`--timeout 30` limits capture inactivity and socket waits, including time
between depth replies. The client reconnects after failures and terminates
both capture processes on exit.

### Live preview and audio

The window opens on the first valid video frame, and its title reports display
FPS. Audio plays automatically on the laptop. Close the window or press Escape
to stop the server. Old images in `test/` are left alone; no new images or audio
files are saved on either device.

Video capture, audio capture, network transmission, preview, playback, and depth
run independently. Queues retain the latest video and at most 200 ms of pending
audio; older queued data is dropped under load. TCP and the audio device may add
further latency. This is live monitoring with separate audio/video clocks,
**not guaranteed lip-synchronized playback**. Use a timestamped media container
if tight A/V synchronization becomes necessary. The audio is not yet connected
to speech recognition or the robot brain.

The implementation uses FFmpeg's [V4L2 and ALSA inputs](https://ffmpeg.org/ffmpeg-devices.html)
and [ffplay](https://ffmpeg.org/ffplay.html) for playback. No new pip packages
are required for webcam/audio capture or playback.

### Depth results

`--no-depth` returns `status: "preview"` with no depth estimates. With depth
enabled, replies contain left/center/right `relative_proximity` (0 = relatively
farther, 1 = relatively nearer), `raw_inverse_depth`, and `preferred_direction`.
Scores use each region's 90th percentile in the middle half of the image,
normalized against that frame's 5th/95th percentiles. These are **not meters,
clearance, or collision probabilities** and cannot be compared across frames.
Flat maps return `uncertain`; failed inference returns `error`.

`frame_id` counts only video frames in the current TCP connection, starting at
1. Gaps are expected because depth samples fewer frames than preview displays.
`processing_ms` measures depth processing time; `server_frame_age_ms` measures
time from full video receipt to result creation, excluding Pi capture and
network transit. Audio packets never increment frame IDs or trigger inference.

Results are advisory only. This pipeline is not wired to motors or the arbiter.
Before movement, add independent onboard obstacle sensing and a motor watchdog
that stops stale commands (~0.5 seconds); Wi-Fi depth cannot provide that safety.

### Local checks without the Pi

```sh
python3 -m unittest test_camera_pipeline
# With the server running:
python3 -m pi.client --host 127.0.0.1 --image /path/to/photo.jpg --once
```

Checks cover fragmented TCP/MJPEG, length limits, invalid audio/JPEG handling,
process cleanup, and audio/video delivery while depth is blocked. They do not
verify physical USB hardware. A synthetic FFmpeg capture/playback integration
check is also available as `python3 -m unittest test_webcam_audio` (requires
ffmpeg/ffplay; uses silent audio output and no webcam or microphone).

Wire format: uint32 big-endian payload length, followed by JPEG bytes **or**
`PCM1` + mono signed 16-bit little-endian audio at 16 kHz (up to 640 audio bytes,
20 ms). Upstream payloads are at most 2 MiB. Downstream JSON replies are at
most 8 KiB. Both directions are independent; only sampled video yields replies.

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
