"""Stream CSI MJPEG to the laptop while receiving depth results independently."""

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

from shared.protocol import MAX_FRAME, MAX_RESULT, receive, send


def mjpeg_frames(chunks):
    """Split rpicam's MJPEG stream, including markers split across reads."""
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
    condition = threading.Condition()
    stopped = threading.Event()
    errors = []
    camera = None
    if not args.image:
        camera = subprocess.Popen([
            "rpicam-vid", "--nopreview", "--timeout", "0", "--codec", "mjpeg",
            "--width", "640", "--height", "480", "--framerate", str(args.fps),
            "--quality", str(args.quality), "--flush", "--output", "-",
        ], stdout=subprocess.PIPE)

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
                def chunks():
                    with selectors.DefaultSelector() as selector:
                        selector.register(camera.stdout, selectors.EVENT_READ)
                        while not stopped.is_set():
                            if not selector.select(args.timeout):
                                raise TimeoutError("camera stopped producing frames")
                            chunk = camera.stdout.read1(65536)
                            if not chunk:
                                return
                            yield chunk
                for jpeg in mjpeg_frames(chunks()):
                    with condition:
                        pending.append(jpeg)
                        condition.notify()
                    if args.once or stopped.is_set():
                        return
                if not stopped.is_set():
                    raise EOFError("camera stream ended")
        except (OSError, EOFError, ValueError) as exc:
            fail(exc)

    def transmit():
        try:
            while not stopped.is_set():
                with condition:
                    condition.wait_for(lambda: pending or stopped.is_set())
                    if stopped.is_set():
                        return
                    jpeg = pending.pop()
                send(sock, jpeg, MAX_FRAME)
                if args.once:
                    return
        except (OSError, ValueError) as exc:
            fail(exc)

    workers = [threading.Thread(target=capture, daemon=True),
               threading.Thread(target=transmit, daemon=True)]
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
        if camera:
            camera.terminate()
            try:
                camera.wait(timeout=2)
            except subprocess.TimeoutExpired:
                camera.kill()
                camera.wait()
        for worker in workers:
            worker.join()
        if camera:
            camera.stdout.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="laptop IP on the hotspot")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--image", type=Path, help="stream a JPEG file instead of using CSI")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--fps", type=int, default=15)
    parser.add_argument("--quality", type=int, default=70)
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("timeout must be positive and finite")
    if not 1 <= args.fps <= 60 or not 1 <= args.quality <= 100:
        parser.error("fps must be 1–60 and quality must be 1–100")
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
