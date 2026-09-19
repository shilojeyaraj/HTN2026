"""CSI JPEG -> relative depth -> three proximity estimates. No motor control."""

import argparse
import io
import json
import logging
from pathlib import Path
import socket
import time

import numpy as np
from PIL import Image

from shared.protocol import MAX_FRAME, MAX_RESULT, receive, send

MODEL = "depth-anything/Depth-Anything-V2-Small-hf"
FRAME_DIR = Path(__file__).resolve().parent.parent / "test"


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


def handle_connection(conn, infer, frame_dir=FRAME_DIR):
    frame_dir.mkdir(parents=True, exist_ok=True)
    while True:
        jpeg = receive(conn, MAX_FRAME)
        start = time.monotonic()
        try:
            with Image.open(io.BytesIO(jpeg)) as image:
                if image.format != "JPEG" or max(image.size) > 1920:
                    raise ValueError("expected JPEG at most 1920 pixels per side")
                rgb = image.convert("RGB")
                path = frame_dir / f"frame-{time.time_ns()}.jpg"
                path.write_bytes(jpeg)
                logging.info("Saved received frame: %s", path)
                result = summarize(infer(rgb))
        except Exception:
            logging.exception("Frame processing failed")
            result = {"status": "error", "relative_proximity": None,
                      "preferred_direction": None}
        result.update(processing_ms=round((time.monotonic() - start) * 1000),
                      advisory_only=True)
        send(conn, json.dumps(result, allow_nan=False).encode(), MAX_RESULT)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--device", default="cpu", help="cpu, cuda, or mps")
    parser.add_argument("--timeout", type=float, default=30)
    args = parser.parse_args()
    if not np.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("timeout must be positive and finite")
    logging.basicConfig(level=logging.INFO)
    infer = load_model(args.device)
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
                    handle_connection(conn, infer)
                except (EOFError, OSError, ValueError) as exc:
                    logging.info("Client disconnected: %s", exc)


if __name__ == "__main__":
    main()
