"""Real multimodal inference on a synthetic image; every actuator is mocked."""

import asyncio
import time
from unittest.mock import AsyncMock, Mock, patch

import cv2
import numpy as np
import pytest

from brain import loop
from brain.state import RobotState
from control.robomaster import RoboMasterController
from perception.vision import aclose_vision_client
from tests.conftest import has_real_key

pytestmark = [pytest.mark.integration,
              pytest.mark.skipif(not has_real_key("GEMINI_API_KEY"), reason="GEMINI_API_KEY not set")]


def test_run_episode_with_fake_robomaster():
    controller = Mock(spec=RoboMasterController)
    controller.get_chassis_state.return_value = {}
    controller.get_camera_state.return_value = {"last_frame_monotonic_s": time.monotonic(), "frame_age_s": 0.01}
    for name in loop.PHYSICAL_ACTIONS | {"stop"}:
        getattr(controller, name).return_value = {"status": "completed"}
    _, jpeg = cv2.imencode(".jpg", np.full((360, 640, 3), 220, dtype=np.uint8))
    async def run():
        try:
            with patch.object(loop, "get_latest_frame", return_value=jpeg.tobytes()), \
                 patch.object(loop.brain, "enqueue_memory"), patch.object(loop, "speak"), \
                 patch.object(loop.brain, "run_tools", new_callable=AsyncMock) as old_planner:
                state = await loop.run_episode(RobotState(current_goal="Inspect the scene safely"), controller)
                assert state.scene_description and state.consecutive_failures == 0
                old_planner.assert_not_awaited()
        finally:
            await aclose_vision_client()
    asyncio.run(run())
