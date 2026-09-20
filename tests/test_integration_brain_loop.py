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


@pytest.mark.parametrize("startup_scan,visible_target", [(False, False), (True, False), (True, True)],
                         ids=["normal", "scan", "target"])
def test_run_episode_with_fake_robomaster(startup_scan, visible_target):
    controller = Mock(spec=RoboMasterController)
    controller.get_chassis_state.return_value = {}
    controller.get_camera_state.side_effect = lambda: {"last_frame_monotonic_s": time.monotonic(), "frame_age_s": 0.01}
    for name in loop.PHYSICAL_ACTIONS | {"stop"}:
        getattr(controller, name).return_value = {"status": "completed"}
    frame = np.full((360, 640, 3), 220, dtype=np.uint8)
    if visible_target:
        cv2.rectangle(frame, (240, 100), (400, 260), (0, 0, 255), -1)
    _, jpeg = cv2.imencode(".jpg", frame)
    async def run():
        try:
            with patch.object(loop, "get_latest_frame", return_value=jpeg.tobytes()), \
                 patch.object(loop.brain, "enqueue_memory"), patch.object(loop, "speak"), \
                 patch.object(loop, "decide_action", wraps=loop.decide_action) as inference, \
                 patch.object(loop.brain, "run_tools", new_callable=AsyncMock) as old_planner:
                state = RobotState(current_goal="Approach the large red rectangle" if visible_target else "Inspect the scene safely",
                                   startup_scan_status="pending" if startup_scan else "completed")
                if startup_scan:
                    await loop.run_episode(state, controller)
                    controller.recenter_arm.assert_called_once_with()
                    controller.move_arm.assert_called_once_with(x_mm=40, y_mm=30)
                await loop.run_episode(state, controller)
                assert state.scene_description and state.consecutive_failures == 0
                inference.assert_awaited_once()
                if startup_scan:
                    if visible_target:
                        assert state.startup_scan_status == "target_found"
                        assert state.startup_scan_rotation_deg == 0
                        assert len(state.world_state.observations) == 1
                    else:
                        controller.turn.assert_not_called()  # HIGH must be observed before turning.
                        controller.move_arm.assert_called_with(x_mm=0, y_mm=30)
                    assert state.world_state.observations[0]["heading_deg"] == 0
                    assert state.world_state.observations[0]["camera_height"] == "LOW"
                old_planner.assert_not_awaited()
        finally:
            await aclose_vision_client()
    asyncio.run(run())
