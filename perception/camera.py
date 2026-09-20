"""RoboMaster camera adapter for the agent-facing perception layer."""

import logging

import cv2

from control.robomaster import RoboMasterController

logger = logging.getLogger(__name__)


def get_latest_frame(controller: RoboMasterController) -> bytes | None:
    """JPEG-encode a fresh buffered frame; never wait on the SDK video decoder."""
    frame = controller.get_latest_frame()
    if frame is None:
        return None
    ok, encoded = cv2.imencode(".jpg", frame)
    if not ok:
        logger.warning("could not JPEG-encode RoboMaster camera frame")
        return None
    return encoded.tobytes()
