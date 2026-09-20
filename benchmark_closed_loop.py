"""Compare real API latency on one synthetic JPEG. Never connects to a robot.

Usage: python benchmark_closed_loop.py --samples 3
Requires Gemini and Backboard keys. Logs old two-call and new one-call timings.
"""

import argparse
import asyncio
import json
import logging
import statistics
import time

import cv2
import numpy as np
from dotenv import load_dotenv

load_dotenv()

from brain.backboard_client import brain
from brain.tools import SYSTEM_PROMPT, VERBS, validate_decision
from perception import vision

logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.samples <= 5:
        parser.error("--samples must be between 1 and 5")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    frame = np.full((360, 640, 3), 220, dtype=np.uint8)
    cv2.rectangle(frame, (400, 140), (520, 270), (0, 0, 180), -1)
    ok, encoded = cv2.imencode(".jpg", frame)
    assert ok
    jpeg = encoded.tobytes()
    context = {"current_goal": "Find the red chair", "robot_pose": {}, "scene_fresh": True,
               "recent_observations": [], "findings": [], "last_actions": [], "mission_context": []}
    old_times, new_times = [], []
    try:
        await brain._ensure_initialized()
        vision.MIN_INTERVAL_S = 0  # Measure inference, excluding the old artificial gap.
        for index in range(args.samples):
            started = time.monotonic()
            description = await asyncio.to_thread(vision.describe_scene, jpeg)
            if not description:
                raise RuntimeError("Baseline vision failed; cannot compare successful inference")
            vision_s = time.monotonic() - started
            brain.thread_id = None  # Independent samples; no unexecuted tool continuation.
            planned = time.monotonic()
            response = await brain._request_planner(json.dumps({**context, "scene_description": description}),
                                                     SYSTEM_PROMPT, VERBS, "off")
            if brain._is_llm_error(response):
                raise RuntimeError("Baseline planner failed; cannot compare successful inference")
            planner_s = time.monotonic() - planned
            old_times.append(vision_s + planner_s)
            logger.info("BENCH sample=%d mode=OLD vision_s=%.3f planner_s=%.3f total_s=%.3f",
                        index + 1, vision_s, planner_s, old_times[-1])
            started = time.monotonic()
            result = validate_decision(await vision.decide_action(jpeg, context))
            new_times.append(time.monotonic() - started)
            logger.info("BENCH sample=%d mode=MULTIMODAL model=%s inference_latency_s=%.3f tool=%s args=%r goal_complete=%s; NOT EXECUTED",
                        index + 1, vision.ACTION_MODEL, new_times[-1], result["tool"], result["args"], result["goal_complete"])
        old, new = statistics.median(old_times), statistics.median(new_times)
        logger.info("BENCH summary samples=%d old_median_s=%.3f new_median_s=%.3f reduction_s=%.3f reduction_pct=%.1f",
                    args.samples, old, new, old - new, 100 * (old - new) / old)
    finally:
        try:
            await brain.aclose()
        finally:
            await vision.aclose_vision_client()


if __name__ == "__main__":
    asyncio.run(main())
