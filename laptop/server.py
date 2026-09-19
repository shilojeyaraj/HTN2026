"""CSI JPEG -> relative depth -> three proximity estimates. No motor control."""

import argparse
from collections import deque
import io
import json
import logging
import socket
import time
import threading

import numpy as np
from PIL import Image

from shared.protocol import MAX_FRAME, MAX_RESULT, receive, send

MODEL = "depth-anything/Depth-Anything-V2-Small-hf"


def summarize(depth):
    depth = np.asarray(depth, dtype=np.float32)
    if depth.ndim != 2 or min(depth.shape) < 6 or not np.isfinite(depth).all():
        raise ValueError("invalid depth map")
    # ponytail: middle half ignores sky/floor; tune ROI for the mounted camera
    # before navigation. Relative monocular scores cannot establish safe clearance.
    roi = depth[depth.shape[0] // 4:3 * depth.shape[0] // 4]
    low, high = np.percentile(roi, [5, 95])
    raw = dict(zip(("left", "center", "right"),
                   (float(np.percentile(part, 90)) for part in np.array_split(roi, 3, axis=1))))
    if high - low <= 1e-6:
        return {"status": "uncertain", "relative_proximity": None,
                "raw_inverse_depth": raw, "preferred_direction": None}
    scores = {key: float(np.clip((value - low) / (high - low), 0, 1))
              for key, value in raw.items()}
    # Higher inverse-depth means nearer. Prefer center on a tie.
    direction = min(("center", "left", "right"), key=scores.get)
    return {"status": "ok", "relative_proximity": scores,
            "raw_inverse_depth": raw, "preferred_direction": direction}


def load_model(device):
    import torch
    from transformers import AutoImageProcessor, AutoModelForDepthEstimation

    processor = AutoImageProcessor.from_pretrained(MODEL)
    model = AutoModelForDepthEstimation.from_pretrained(MODEL).to(device).eval()

    def infer(image):
        inputs = processor(images=image, return_tensors="pt").to(device)
        with torch.inference_mode():
            return model(**inputs).predicted_depth[0].float().cpu().numpy()

    return infer


def handle_connection(conn, infer, show_frame=lambda image: None):
    pending = deque(maxlen=1)
    condition = threading.Condition()
    stopped = threading.Event()
    errors = []

    def receive_frames():
        frame_id = 0
        try:
            while not stopped.is_set():
                jpeg = receive(conn, MAX_FRAME)
                frame_id += 1
                received_at = time.monotonic()
                try:
                    with Image.open(io.BytesIO(jpeg)) as image:
                        if image.format != "JPEG" or max(image.size) > 1920:
                            raise ValueError("expected JPEG at most 1920 pixels per side")
                        rgb = image.convert("RGB")
                    show_frame(rgb)
                except Exception:
                    logging.exception("Frame decoding failed")
                    rgb = None
                with condition:
                    pending.append((frame_id, received_at, rgb))
                    condition.notify()
        except (EOFError, OSError, ValueError) as exc:
            with condition:
                errors.append(exc)
                condition.notify()

    reader = threading.Thread(target=receive_frames, daemon=True)
    reader.start()
    try:
        while True:
            with condition:
                condition.wait_for(lambda: pending or errors)
                if errors:
                    raise errors[0]
                frame_id, received_at, rgb = pending.pop()
            start = time.monotonic()
            try:
                if rgb is None:
                    raise ValueError("invalid JPEG")
                result = (summarize(infer(rgb)) if infer is not None else
                          {"status": "preview", "relative_proximity": None,
                           "preferred_direction": None})
            except Exception:
                logging.exception("Frame inference failed")
                result = {"status": "error", "relative_proximity": None,
                          "preferred_direction": None}
            result.update(frame_id=frame_id,
                          processing_ms=round((time.monotonic() - start) * 1000),
                          server_frame_age_ms=round((time.monotonic() - received_at) * 1000),
                          advisory_only=True)
            send(conn, json.dumps(result, allow_nan=False).encode(), MAX_RESULT)
    finally:
        stopped.set()
        try:
            conn.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        reader.join()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--device", default="cpu", help="cpu, cuda, or mps")
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--no-preview", action="store_true", help="run without a desktop window")
    parser.add_argument("--no-depth", action="store_true", help="preview only; skip model loading and inference")
    args = parser.parse_args()
    if not np.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("timeout must be positive and finite")
    logging.basicConfig(level=logging.INFO)
    if args.no_preview:
        serve(args)
    else:
        from laptop.preview import run_preview
        run_preview(lambda show_frame: serve(args, show_frame))


def serve(args, show_frame=lambda image: None):
    infer = None if args.no_depth else load_model(args.device)
    # ponytail: one Pi at a time; concurrent clients only if a second robot arrives.
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((args.host, args.port))
        server.listen(1)
        logging.info("Ready on %s:%s", args.host, args.port)
        while True:
            conn, address = server.accept()
            with conn:
                conn.settimeout(args.timeout)
                logging.info("Pi connected: %s", address)
                try:
                    handle_connection(conn, infer, show_frame)
                except (EOFError, OSError, ValueError) as exc:
                    logging.info("Client disconnected: %s", exc)
                    show_frame(None)


if __name__ == "__main__":
    main()
