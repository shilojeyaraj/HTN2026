"""Capture one JPEG, send it, print the result, repeat. Requires only Python/rpicam."""

import argparse
import json
import math
from pathlib import Path
import socket
import subprocess
import tempfile
import time

from shared.protocol import MAX_FRAME, MAX_RESULT, receive, send


def capture(path):
    # ponytail: restarting rpicam costs startup time; use persistent capture if FPS matters.
    subprocess.run([
        "rpicam-still", "--nopreview", "--timeout", "500",
        "--width", "640", "--height", "480", "--encoding", "jpg",
        "--output", str(path),
    ], check=True, timeout=10, stdout=subprocess.DEVNULL)
    return path.read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True, help="laptop IP on the hotspot")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--image", type=Path, help="send a JPEG file instead of using CSI")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--interval", type=float, default=0.2)
    args = parser.parse_args()
    if not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("timeout must be positive and finite")
    if not math.isfinite(args.interval) or args.interval < 0:
        parser.error("interval must be nonnegative and finite")
    with tempfile.TemporaryDirectory() as directory:
        while True:
            try:
                with socket.create_connection((args.host, args.port), timeout=args.timeout) as sock:
                    while True:
                        start = time.monotonic()
                        jpeg = args.image.read_bytes() if args.image else capture(Path(directory) / "frame.jpg")
                        send(sock, jpeg, MAX_FRAME)
                        result = json.loads(receive(sock, MAX_RESULT))
                        if not isinstance(result, dict) or result.get("status") not in {"ok", "uncertain", "error"}:
                            raise ValueError("invalid server result")
                        result["capture_roundtrip_ms"] = round((time.monotonic() - start) * 1000)
                        print(json.dumps(result), flush=True)
                        if args.once:
                            return
                        time.sleep(args.interval)
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
