# htn2026 rover

Autonomous voice-interactive rover built at Hack the North 2026. See [CLAUDE.md](CLAUDE.md) for the full architecture and project context.

## Current milestone: USB webcam + microphone → laptop

A USB webcam plugs into the Pi 5. Its video and microphone audio stream to
one laptop over TCP. The laptop opens a live video window and transcribes microphone audio locally.
Recognized text appears below the video and as JSON in the laptop terminal.
Optional monocular depth runs independently. There is no audio playback.
Nothing is recorded to disk unless `--record` is enabled on the laptop.
Run commands from the repository root.

### 1. Laptop

`faster-whisper>=1.1,<2` is declared in `laptop/requirements.txt`. The root
`requirements.txt` includes that file, so either install path gets transcription.
For just webcam streaming/transcription, prefer the laptop requirements: the
root file additionally installs dependencies for the older robot/voice stack.

The laptop needs the Python dependencies below; ffplay is no longer used.
The Pi still needs FFmpeg for webcam/microphone capture. Python setup:

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
`--no-transcription` skips speech model loading and discards received audio.
`--no-preview` hides video but keeps terminal transcription. The old `--mute`
flag is removed because audio is never played. Tkinter/Pillow provide the desktop preview; Python needs Tk
support (`python3-tk` on Debian/Ubuntu, or Tk support in a custom Python build).

Both devices must be on the same network. Allow inbound TCP port 8765 if
needed. This prototype is unauthenticated; use a trusted private network.
Without `--host`, the server binds only to localhost.

### System dependencies on another Unix machine

The **receiver** is tested on Linux with Python 3.13. Use a 64-bit Python with
available PyTorch, CTranslate2, ONNX Runtime, and PyAV wheels. Linux/macOS have
[CTranslate2 binary packages](https://opennmt.net/CTranslate2/installation.html);
this does not guarantee every Unix/CPU combination. macOS has not been tested
in this project. BSD and unsupported/old Linux distributions may require
native builds and are not an out-of-the-box target.

**Debian/Ubuntu laptop**, before creating the virtual environment:

```sh
sudo apt update
sudo apt install python3 python3-venv python3-pip python3-tk libgomp1 git rsync openssh-client
```

**macOS laptop**, using matching Homebrew Python/Tk versions:

```sh
brew install python@3.13 python-tk@3.13 git rsync
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r laptop/requirements.txt
```

[Homebrew's Tk package](https://formulae.brew.sh/formula/python-tk%403.13)
must match the Python used to create the venv. For pyenv/custom builds, install
Tcl/Tk development libraries before building Python; installing pip packages
cannot repair a Python built without `_tkinter`. Verify in the activated venv:

```sh
python -m tkinter
python -c "import faster_whisper, torch, torchvision; from PIL import ImageTk; print('Imports OK')"
```

The first command should open a test window. Preview requires a graphical
desktop session (and a working display connection on Linux). On headless SSH
sessions use `--no-preview`; transcripts still print to the terminal.

**Pi/capture host:** the current capture implementation is Linux-only because
it uses V4L2 and ALSA. It requires system `ffmpeg`, with those input backends,
and camera/microphone device permissions. `v4l-utils` and `alsa-utils` provide
the discovery commands below. Check backends with `ffmpeg -hide_banner -devices`.
On Raspberry Pi OS, if opening the device reports permission denied, check
membership of the `video`/`audio` groups and log in again after adding access.
Capturing directly on macOS would need an AVFoundation capture implementation;
installing FFmpeg alone does not make this Pi client portable to macOS.

**Not required for normal laptop transcription:** system FFmpeg/ffplay,
PortAudio, CUDA, or a cloud API key. Faster-whisper's pip dependencies provide
the audio decoding/inference libraries. The synthetic integration test does
require system `ffmpeg` (`sudo apt install ffmpeg` or `brew install ffmpeg`).
The older `voice/stt.py` path uses `sounddevice` and separately needs PortAudio
on Linux (`sudo apt install libportaudio2`); it is not used by this receiver.

First startup needs internet access to download model weights and writable
cache space. Speech weights default to `.cache/whisper/`; optional depth uses
the Hugging Face cache. On a new machine, use a persistent writable cache such
as `HF_HOME="$HOME/.cache/huggingface"` rather than this laptop's `/tmp` cache.
Both machines need network reachability on TCP 8765. SSH/rsync are needed only
for the documented sync workflow, not for streaming itself.

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
v4l2-ctl --device /dev/video8 --list-formats-ext
arecord -l
```

Select the webcam's **capture** device (some webcams expose multiple video
nodes). Select its audio card from `arecord -l`; audio and video device numbers
are independent. A webcam without a built-in mic needs a separate USB mic.

### 4. Start on the Pi

The confirmed devices for this Pi are `/dev/video8` and microphone card 2,
device 0. Device numbers may change after reconnecting USB hardware:

```sh
cd ~/HTN2026
python3 -m pi.client --host 172.20.10.3 --video-device /dev/video8 --audio-device plughw:2,0 --fps 15
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

### Live preview and transcription

The window opens on the first valid video frame, and its title reports display
FPS. Provisional transcripts update while speech is arriving, then finalize after
a pause. Provisional wording may change as more context arrives. Close the window or press Escape
to stop the server. Old images in `test/` are left alone; no new images or audio
files are saved on either device unless laptop recording is enabled.

Video capture, audio capture, network transmission, preview, transcription,
and depth run independently. Queues retain the latest video and at most 200 ms of pending
audio; older queued data is dropped under load. TCP and the audio device may add
further latency. Speech processing has its own bounded queue described below.
Transcripts are informational; they do not call the reasoning model or motors.

The implementation uses FFmpeg's [V4L2 and ALSA inputs](https://ffmpeg.org/ffmpeg-devices.html)
and [faster-whisper](https://github.com/SYSTRAN/faster-whisper) for local
CPU INT8 transcription (two inference threads). Install the updated laptop
requirements before restarting; no Pi changes or re-sync are needed for STT.

### Transcription setup and tuning

```sh
venv/bin/python -m pip install -r laptop/requirements.txt
venv/bin/python -m laptop.server --host 0.0.0.0 --no-depth
```

The first start downloads the English `base.en` speech model into the ignored
project folder `.cache/whisper/`. Wait for `Ready`; after download, recognition
runs entirely on the laptop. Audio is not sent to a cloud transcription API.
`--stt-cache /writable/path` changes the cache. Use `--stt-model tiny.en` for
less compute, `small.en` for a larger English model, or `base` for multilingual
speech. These tradeoffs need testing with the actual microphone/noise level.

Recognition is fully hands-off: no push-to-talk button. We attempt a provisional
update every 0.8 seconds of incoming speech (`--partial-interval` adjusts this).
This is repeated recognition of a growing utterance, not token-by-token model
streaming; actual update latency includes inference time. More frequent updates
use more CPU. Only the newest pending partial is kept, finals take priority,
and partials still computing after their utterance ends are suppressed.

We keep 200 ms of audio before speech starts, finish an utterance after 0.7 s
of quiet, and split continuous speech at 10 s. Very short sounds (<200 ms)
are ignored. A simple RMS gate starts/stops clips; Whisper's VAD additionally
filters each clip. `--speech-threshold 0.015` controls the RMS gate: lower it
for quiet speech, raise it if background noise keeps triggering recognition.
The 10-second cap can split words; this is a minimal utterance-based pipeline.

Up to two completed utterances can wait behind the active transcription.
If inference falls behind, the oldest pending utterance is dropped with a
warning so video remains responsive. Disconnect flushes the last utterance
and drains the queue before accepting another Pi. Transcription itself creates
no audio or transcript files; optional recording separately saves received media. Terminal JSON includes `type: "transcript"`, `utterance_id`,
`text`, and `final: false` for provisional updates / `final: true` for completed
utterances. Replace text with the same utterance ID rather than appending each
revision. IDs restart per TCP connection. An empty final clears a provisional
that was not confirmed; failures emit an empty final with an `error` field.
The preview labels provisional text and replaces it on finalization. Silence produces no text output.
Speech recognition can make mistakes, especially in noisy rooms; these texts
are not authorized movement commands.

### Optional laptop recording

Add `--record` to the laptop server command:

```sh
venv/bin/python -m laptop.server --host 0.0.0.0 --no-depth --record
# Optionally choose another output directory:
venv/bin/python -m laptop.server --host 0.0.0.0 --no-depth --record --record-dir /path/to/recordings
```

Each Pi connection creates a unique UTC-timestamped `.mkv` file in the project
`recordings/` directory (ignored by Git). Reconnecting creates a new file.
The recording contains received webcam video and microphone audio, including
video frames skipped by depth inference. It uses PyAV (already installed with
faster-whisper, now declared explicitly) to copy MJPEG and PCM without
re-encoding. No additional system FFmpeg installation is required on the laptop.
Use an MKV-capable player such as VLC to review it. Transcript text is not
embedded in the file.

Recording is independent of `--no-depth`, `--no-preview`, and
`--no-transcription`. Pi `--no-audio` means there is no microphone audio to save.
Media timestamps reflect laptop receipt time; camera capture timestamps are
not transmitted, so exact A/V synchronization and reconstruction of frames
lost before receipt are not guaranteed. Disk writes add I/O to reception;
use a fast local disk with enough free space. Recording errors close the
connection and are logged rather than silently dropping media.

Stop the Pi client, close the preview window, or use Ctrl+C on the server to
finalize the file. Closing the preview now requests receiver shutdown and waits
for recording finalization (and pending transcription). Force-killing the
process or losing power can leave an unfinished file. Existing recordings are
never overwritten or automatically deleted. No Pi code sync is needed.

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
verify physical USB hardware. A synthetic FFmpeg capture/transcription integration
check is also available as `python3 -m unittest test_webcam_audio` (requires
ffmpeg; uses synthetic devices and a stub recognizer). Speech segmentation and
queue behavior are checked with `python3 -m unittest test_transcription`.
Recording and file-finalization checks: `python3 -m unittest test_recording`.

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
