"""Stream USB webcam video and microphone audio; receive depth independently."""

import argparse
from collections import deque
import json
import math
from pathlib import Path
import selectors
import socket
import subprocess
import threading
import time

from shared.protocol import AUDIO_CHUNK, AUDIO_PREFIX, AUDIO_RATE, MAX_FRAME, MAX_RESULT, receive, send


def camera_command(args):
    command = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin",
               "-f", "v4l2", "-input_format", args.input_format,
               "-framerate", str(args.fps), "-video_size", f"{args.width}x{args.height}",
               "-i", args.video_device, "-an"]
    if args.input_format == "mjpeg":
        command += ["-c:v", "copy"]  # Use the webcam's JPEG encoder without re-encoding.
    else:
        command += ["-c:v", "mjpeg", "-threads", "1", "-q:v", str(31 - round(args.quality * 29 / 100))]
    return command + ["-f", "mjpeg", "-flush_packets", "1", "pipe:1"]


def pipe_chunks(process, stopped, timeout):
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        while not stopped.is_set():
            if not selector.select(timeout):
                raise TimeoutError("capture device stopped producing data")
            chunk = process.stdout.read1(65536)
            if not chunk:
                return
            yield chunk


def mjpeg_frames(chunks):
    """Split FFmpeg's MJPEG stream, including markers split across reads."""
    data = bytearray()
    for chunk in chunks:
        data.extend(chunk)
        while True:
            start = data.find(b"\xff\xd8")
            if start < 0:
                if len(data) > MAX_FRAME:
                    raise ValueError("MJPEG frame start missing")
                break
            del data[:start]
            end = data.find(b"\xff\xd9", 2)
            if end < 0:
                if len(data) > MAX_FRAME:
                    raise ValueError("MJPEG frame exceeds size limit")
                break
            size = end + 2
            if size > MAX_FRAME:
                raise ValueError("MJPEG frame exceeds size limit")
            yield bytes(data[:size])
            del data[:size]
    if data:
        raise EOFError("truncated MJPEG stream")


def stream(sock, args):
    pending = deque(maxlen=1)
    audio_pending = deque(maxlen=10)  # At most 200 ms; drop oldest audio on a slow link.
    condition = threading.Condition()
    stopped = threading.Event()
    errors = []
    camera = None
    microphone = None
    if not args.image:
        camera = subprocess.Popen(camera_command(args), stdout=subprocess.PIPE)
        try:
            if not args.no_audio and not args.once:
                microphone = subprocess.Popen([
                    "ffmpeg", "-hide_banner", "-loglevel", "warning", "-nostdin",
                    "-f", "alsa", "-channels", "1", "-i", args.audio_device,
                    "-ac", "1", "-ar", str(AUDIO_RATE), "-c:a", "pcm_s16le",
                    "-f", "s16le", "-flush_packets", "1", "pipe:1",
                ], stdout=subprocess.PIPE)
        except OSError:
            camera.kill()
            camera.wait()
            camera.stdout.close()
            raise

    def fail(exc):
        errors.append(exc)
        stopped.set()
        with condition:
            condition.notify_all()
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def capture():
        try:
            if args.image:
                jpeg = args.image.read_bytes()
                if not 0 < len(jpeg) <= MAX_FRAME:
                    raise ValueError("invalid JPEG file size")
                while not stopped.is_set():
                    with condition:
                        pending.append(jpeg)
                        condition.notify()
                    if args.once or stopped.wait(1 / args.fps):
                        return
            else:
                for jpeg in mjpeg_frames(pipe_chunks(camera, stopped, args.timeout)):
                    with condition:
                        pending.append(jpeg)
                        condition.notify()
                    if args.once or stopped.is_set():
                        return
                if not stopped.is_set():
                    raise EOFError("camera stream ended")
        except (OSError, EOFError, ValueError) as exc:
            fail(exc)

    def capture_audio():
        try:
            data = bytearray()
            for chunk in pipe_chunks(microphone, stopped, args.timeout):
                data.extend(chunk)
                while len(data) >= AUDIO_CHUNK:
                    packet = AUDIO_PREFIX + bytes(data[:AUDIO_CHUNK])
                    del data[:AUDIO_CHUNK]
                    with condition:
                        audio_pending.append(packet)
                        condition.notify()
            if not stopped.is_set():
                raise EOFError("microphone stream ended; check --audio-device or use --no-audio")
        except (OSError, EOFError, ValueError) as exc:
            fail(exc)

    def transmit():
        try:
            while not stopped.is_set():
                with condition:
                    condition.wait_for(lambda: pending or audio_pending or stopped.is_set())
                    if stopped.is_set():
                        return
                    packets = list(audio_pending)
                    audio_pending.clear()
                    if pending:
                        packets.append(pending.pop())
                for packet in packets:
                    send(sock, packet, MAX_FRAME)
                if args.once:  # Single-frame diagnostic does not capture audio.
                    return
        except (OSError, ValueError) as exc:
            fail(exc)

    workers = [threading.Thread(target=capture, daemon=True),
               threading.Thread(target=transmit, daemon=True)]
    if microphone:
        workers.append(threading.Thread(target=capture_audio, daemon=True))
    for worker in workers:
        worker.start()
    try:
        while True:
            result = json.loads(receive(sock, MAX_RESULT))
            if not isinstance(result, dict) or result.get("status") not in {"ok", "uncertain", "error", "preview"}:
                raise ValueError("invalid server result")
            print(json.dumps(result), flush=True)
            if args.once:
                return
    except (OSError, EOFError):
        if errors:
            raise errors[0]
        raise
    finally:
        stopped.set()
        with condition:
            condition.notify_all()
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        for process in (camera, microphone):
            if process:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        for worker in workers:
            worker.join()
        for process in (camera, microphone):
            if process:
                process.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="laptop IP on the hotspot")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--image", type=Path, help="stream a JPEG file instead of the webcam (no audio)")
    parser.add_argument("--video-device", default="/dev/video0")
    parser.add_argument("--audio-device", default="default", help="ALSA input, e.g. plughw:1,0")
    parser.add_argument("--no-audio", action="store_true")
    parser.add_argument("--input-format", choices=("mjpeg", "yuyv422"), default="mjpeg")
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--height", type=int, default=480)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--quality", type=int, default=70)
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("timeout must be positive and finite")
    if not 1 <= args.fps <= 60 or not 1 <= args.quality <= 100:
        parser.error("fps must be 1–60 and quality must be 1–100")
    if not 1 <= args.width <= 1920 or not 1 <= args.height <= 1920:
        parser.error("width and height must be 1–1920")
    while True:
        try:
            with socket.create_connection((args.host, args.port), timeout=args.timeout) as sock:
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 65536)
                stream(sock, args)
            if args.once:
                return
        except (OSError, EOFError, ValueError, subprocess.SubprocessError) as exc:
            print(json.dumps({"status": "error", "command": "stop", "error": str(exc)}), flush=True)
            if args.once:
                raise SystemExit(1)
            time.sleep(1)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print('{"status":"stopped","command":"stop"}', flush=True)
