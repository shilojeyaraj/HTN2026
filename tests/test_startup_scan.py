"""Offline startup scan, local semantic memory, and post-scan navigation checks."""

import asyncio
import json
import logging
import time
from unittest.mock import call

import pytest

from brain import config, loop
from brain.state import RobotState
from brain.tools import MULTIMODAL_PROMPT, validate_decision
from brain.world_state import WorldState
from control.robomaster import RoboMasterError
from shared.inference import InferenceUnavailable
from tests.test_multimodal_loop import decision, setup_loop


def detection(kind="chair", description="Red chair with a white stripe", **extra):
    return {"type": kind, "description": description, "distance": "medium",
            "confidence": 0.95, "status": "observed", "matched_id": None, **extra}


def semantic(entities=None, room_features=None, quality="good"):
    return {"view_quality": quality, "entities": entities or [], "room_features": room_features or []}


@pytest.fixture
def scan_loop(setup_loop, monkeypatch):
    monkeypatch.setattr(loop, "STARTUP_SCAN_ENABLED", True)
    controller, camera, model, memory = setup_loop
    camera.side_effect = lambda _: f"jpeg-{time.monotonic_ns()}".encode()
    model.return_value = decision(None, {}, target_visible=False, world_observation=semantic())
    memory.enqueue_memory.side_effect = AssertionError("startup must not call Backboard")
    return controller, camera, model, memory


@pytest.mark.parametrize("goal", [None, "Explore the room"])
def test_full_scan_is_fresh_fixed_direction_and_passes_local_summary(goal, scan_loop, caplog):
    controller, camera, model, memory = scan_loop
    state = RobotState(current_goal=goal)
    frames = []

    def observe(jpeg, context):
        frames.append(jpeg)
        heading = context["world_state"]["robot"]["heading_deg"]
        assert context["startup_scan"]["active"]
        assert heading == ((len(frames) - 1) // 2) * 60
        assert context["world_state"]["robot"]["camera_height"] == ("LOW" if len(frames) % 2 else "HIGH")
        assert controller.turn.call_count == (len(frames) - 1) // 2
        entities, features = [], []
        if heading in {120, 180}:
            existing = context["world_state"]["entities"]
            entities = [detection(matched_id=existing[0]["id"] if existing else None)]
        if heading == 0:
            existing = context["world_state"]["room_features"]
            features = [detection("wall", "Nearby wall", distance="near",
                                  matched_id=existing[0]["id"] if existing else None)]
        if heading == 240:
            existing = [f for f in context["world_state"]["room_features"] if f["type"] == "doorway"]
            features = [detection("doorway", "Open doorway", matched_id=existing[0]["id"] if existing else None)]
        # Even an unexpected planner movement cannot replace the fixed scan turn.
        return decision("forward", {"distance_m": 0.5}, observation=f"Scene at {heading}", target_visible=False,
                        world_observation=semantic(entities, features))

    model.side_effect = observe

    async def run():
        await loop.run_episode(state, controller)
        controller.recenter_arm.assert_called_once_with()
        controller.move_arm.assert_called_once_with(x_mm=40, y_mm=30)
        camera.assert_not_called()
        for _ in range(12):
            await asyncio.wait_for(loop.run_episode(state, controller), timeout=0.5)
        assert state.startup_scan_status == "completed"
        assert state.startup_scan_rotation_deg == 360
        assert state.world_state.robot == {"heading_deg": 0, "camera_height": "HIGH"}
        assert state.world_state.searched_headings == [0, 60, 120, 180, 240, 300]
        chair, = state.world_state.entities
        assert chair["first_seen_heading_deg"] == 120 and chair["last_seen_heading_deg"] == 180
        assert chair["first_seen_at"] <= chair["last_seen_at"]
        assert len(state.world_state.room_features) == 2
        assert len(set(frames)) == camera.call_count == model.await_count == 12
        assert [obs["camera_height"] for obs in state.world_state.observations] == ["LOW", "HIGH"] * 6
        assert controller.move_arm.call_args_list == ([call(x_mm=40, y_mm=30)]
                + [call(x_mm=0, y_mm=30), call(x_mm=0, y_mm=-30)] * 5 + [call(x_mm=0, y_mm=30)])
        assert controller.turn.call_args_list == [call(degrees=60)] * 6
        controller.forward.assert_not_called()
        memory.enqueue_memory.assert_not_called()
        assert state.finished_goal is None

        # Later goal receives startup bearings even though goal-relative heading resets.
        memory.enqueue_memory.side_effect = None
        model.side_effect = None
        state.last_user_command = "turn right 30"
        await loop.run_episode(state, controller)
        state.current_goal = "Approach the red chair"
        model.return_value = decision("turn", {"degrees": -90}, target_visible=False)
        await loop.run_episode(state, controller)
        context = model.call_args.args[1]
        assert context["world_state"]["robot"]["heading_deg"] == 330
        assert context["relative_heading_deg"] == 0
        assert "Red chair" in context["world_summary"] and "Open doorway" in context["world_summary"]
        assert not context["startup_scan"]["active"]
        calls = model.await_count
        controller.get_camera_state.side_effect = None
        controller.get_camera_state.return_value = {"last_frame_monotonic_s": state.last_frame_at}
        model.return_value = decision("forward", {"distance_m": 0.2})
        await loop.run_episode(state, controller)
        assert model.await_count == calls
        controller.forward.assert_not_called()

        controller.get_camera_state.side_effect = lambda: {"last_frame_monotonic_s": time.monotonic()}
        state.retry_at = 0
        model.return_value = decision("move_arm", {"x_mm": 0, "y_mm": -20})
        await loop.run_episode(state, controller)
        assert state.world_state.robot["camera_height"] == "ADJUSTED"
        model.return_value = decision("forward", {"distance_m": 0.2})
        await loop.run_episode(state, controller)
        assert state.world_state.bearings_stale
        controller.recenter_arm.assert_called_once()

    with caplog.at_level(logging.INFO):
        asyncio.run(run())
    for text in ("Startup scan started", "home is not a forward-looking", "camera moved to LOW", "camera moved to HIGH", "heading_deg=120",
                 "summary=Scene at", "WorldState new entities", "WorldState updated entities",
                 "Startup scan completed", "final semantic summary"):
        assert text in caplog.text
    assert "re-perceive BEFORE" in MULTIMODAL_PROMPT


def test_scan_waits_for_post_motion_frame_and_retries_perception_without_turning(scan_loop):
    controller, camera, model, _ = scan_loop
    state = RobotState(current_goal="Explore")

    async def run():
        await loop.run_episode(state, controller)
        controller.get_camera_state.side_effect = None
        controller.get_camera_state.return_value = {"last_frame_monotonic_s": state.last_frame_at}
        await loop.run_episode(state, controller)
        model.assert_not_awaited()
        controller.turn.assert_not_called()
        assert not state.world_state.observations
        controller.get_camera_state.side_effect = lambda: {"last_frame_monotonic_s": time.monotonic()}
        model.return_value = decision(None, {})  # Scan requires structured semantics.
        state.retry_at = 0
        await loop.run_episode(state, controller)
        assert state.consecutive_failures == 1 and not state.world_state.observations
        controller.turn.assert_not_called()
        model.return_value = decision(None, {}, target_visible=False, world_observation=semantic(quality="poor"))
        state.retry_at = 0
        await loop.run_episode(state, controller)
        controller.turn.assert_not_called()
        assert state.world_state.robot["camera_height"] == "HIGH"
        assert state.world_state.observations[0]["view_quality"] == "poor"
        assert "Unclear views" in state.world_state.summary()
        # The high image must also arrive after the height adjustment.
        controller.get_camera_state.side_effect = None
        controller.get_camera_state.return_value = {"last_frame_monotonic_s": state.last_frame_at}
        await loop.run_episode(state, controller)
        controller.turn.assert_not_called()
        controller.get_camera_state.side_effect = lambda: {"last_frame_monotonic_s": time.monotonic()}
        model.return_value = decision(None, {}, target_visible=False, world_observation=semantic())
        state.retry_at = 0
        await loop.run_episode(state, controller)
        controller.turn.assert_called_once_with(degrees=60)
        controller.recenter_arm.assert_called_once()

    asyncio.run(run())


@pytest.mark.parametrize("view_index", [0, 1, 4, 5, 11])
def test_visible_target_exits_at_either_height_and_approaches_without_extra_inference(view_index, scan_loop, caplog):
    controller, camera, model, memory = scan_loop
    state = RobotState(current_goal="Find the red chair and drive towards it")

    async def run():
        await loop.run_episode(state, controller)
        for _ in range(view_index):
            await loop.run_episode(state, controller)
        heading = state.world_state.robot["heading_deg"]
        height = state.world_state.robot["camera_height"]
        camera_moves = controller.move_arm.call_count
        model.return_value = decision("forward", {"distance_m": 4}, target_visible=True,
                                      search_active=True, observation="The red chair is ahead; the path is clear.",
                                      world_observation=semantic([detection()]))
        await loop.run_episode(state, controller)
        assert state.startup_scan_status == "target_found"
        assert state.startup_scan_rotation_deg == heading == (view_index // 2) * 60
        assert height == ("LOW" if view_index % 2 == 0 else "HIGH")
        assert controller.turn.call_count == view_index // 2
        assert controller.move_arm.call_count == camera_moves
        controller.forward.assert_called_once_with(0.75)  # Existing bounds still apply.
        assert model.await_count == camera.call_count == view_index + 1
        assert len(state.world_state.observations) == view_index + 1
        assert state.world_state.entities[0]["last_seen_heading_deg"] == heading
        assert state.recent_observations.count(state.scene_description) == 1
        assert not state.search_active and not state.scene_fresh and state.finished_goal is None
        memory.enqueue_memory.assert_not_called()

        # Handoff does not permit another motion on the consumed image.
        controller.get_camera_state.side_effect = None
        controller.get_camera_state.return_value = {"last_frame_monotonic_s": state.last_frame_at}
        await loop.run_episode(state, controller)
        assert model.await_count == view_index + 1
        controller.forward.assert_called_once()

        # Losing the target later uses normal planning, never resumes the fixed scan.
        memory.enqueue_memory.side_effect = None
        controller.get_camera_state.side_effect = lambda: {"last_frame_monotonic_s": time.monotonic()}
        state.retry_at = 0
        model.return_value = decision("turn", {"degrees": -15}, target_visible=False, search_active=True)
        await loop.run_episode(state, controller)
        context = model.call_args.args[1]
        assert context["startup_scan"] == {"active": False, "step_deg": 60,
                                           "status": "target_found", "rotation_deg": heading}
        controller.turn.assert_called_with(degrees=-15)
        assert controller.move_arm.call_count == camera_moves
        assert state.startup_scan_rotation_deg == heading and state.search_active

    with caplog.at_level(logging.INFO):
        asyncio.run(run())
    assert "Startup scan ended early: target visible" in caplog.text
    assert "Startup scan completed:" not in caplog.text


def test_unrelated_object_without_a_mission_does_not_end_scan(scan_loop):
    controller, _, model, _ = scan_loop
    state = RobotState()
    model.return_value = decision("forward", {"distance_m": 0.2}, target_visible=True,
                                  world_observation=semantic([detection()]))

    async def run():
        await loop.run_episode(state, controller)
        await loop.run_episode(state, controller)

    asyncio.run(run())
    assert state.startup_scan_status == "scanning"
    assert state.world_state.robot["camera_height"] == "HIGH"
    controller.forward.assert_not_called()


def test_malformed_target_detection_cannot_end_scan_or_approach(scan_loop):
    controller, _, model, _ = scan_loop
    state = RobotState(current_goal="Approach the red chair")

    async def run():
        await loop.run_episode(state, controller)
        model.return_value = decision("forward", {"distance_m": 0.2}, target_visible="true",
                                      world_observation=semantic([detection()]))
        await loop.run_episode(state, controller)

    asyncio.run(run())
    assert state.startup_scan_status == "scanning" and not state.world_state.observations
    assert state.consecutive_failures == 1
    controller.forward.assert_not_called()
    controller.turn.assert_not_called()
    controller.move_arm.assert_called_once_with(x_mm=40, y_mm=30)


@pytest.mark.parametrize("failure", ["camera", "turn", "manual"])
def test_scan_failure_or_manual_override_does_not_fake_coverage_or_replay_motion(failure, scan_loop):
    controller, _, model, _ = scan_loop
    state = RobotState(current_goal="Explore")

    async def run():
        if failure == "camera":
            controller.recenter_arm.side_effect = RoboMasterError("arm unavailable")
        else:
            await loop.run_episode(state, controller)
            if failure == "turn":
                await loop.run_episode(state, controller)  # LOW observed; now at HIGH.
                controller.turn.side_effect = RoboMasterError("partial turn")
            else:
                state.last_user_command = "turn right 30"
                await loop.run_episode(state, controller)
        with pytest.raises(InferenceUnavailable):
            await loop.run_episode(state, controller)
        calls = controller.turn.call_count
        with pytest.raises(InferenceUnavailable):
            await loop.run_episode(state, controller)
        assert controller.turn.call_count == calls
        assert state.startup_scan_status == "failed" and state.startup_scan_rotation_deg == 0
        if failure == "turn":
            assert state.world_state.robot["heading_deg"] is None
        if failure != "manual":
            controller.stop.assert_called_once()

    asyncio.run(run())


def test_conservative_identity_validation_and_bounded_local_history():
    world = WorldState()
    world.observe("Red chair", semantic([detection()]), 1)
    chair_id = world.entities[0]["id"]
    world.robot["heading_deg"] = 60
    world.observe("Same red chair", semantic([detection(matched_id=chair_id)]), 2)
    assert len(world.entities) == 1 and world.entities[0]["last_seen_heading_deg"] == 60
    world.observe("Two possible chairs", semantic([detection(), detection(matched_id=chair_id, confidence=0.5)]), 3)
    assert len(world.entities) == 3  # Similarity or uncertain identity cannot force a merge.
    for i in range(40):
        world.observe("Open space", semantic(), i + 4)
    assert len(world.observations) == 36
    for extra in ({"x": 1, "y": 2}, {"confidence": float("nan")}, {"distance": "2m"}):
        with pytest.raises(ValueError):
            validate_decision(decision(None, {}, world_observation=semantic([detection(**extra)])))
    json.dumps(world.context(), allow_nan=False)


@pytest.mark.parametrize("group", ["entities", "room_features"])
def test_detection_limit_is_enforced_locally_without_gemini_array_bounds(group):
    from brain.tools import DECISION_SCHEMA
    assert "maxItems" not in DECISION_SCHEMA["properties"]["world_observation"]["properties"][group]
    observation = semantic()
    observation[group] = [detection("furniture")] * 24
    validate_decision(decision(None, {}, world_observation=observation))
    observation[group].append(detection("furniture"))
    with pytest.raises(ValueError, match="at most 24"):
        validate_decision(decision(None, {}, world_observation=observation))


def test_cancelled_scan_stops_and_cannot_resume_an_unknown_arc(scan_loop):
    controller, _, model, _ = scan_loop
    state = RobotState(current_goal="Explore")

    async def run():
        await loop.run_episode(state, controller)
        await loop.run_episode(state, controller)  # LOW observed; now at HIGH.
        controller.turn.side_effect = asyncio.CancelledError
        with pytest.raises(asyncio.CancelledError):
            await loop.run_episode(state, controller)
        assert state.startup_scan_status == "failed"
        assert state.world_state.robot["heading_deg"] is None
        controller.stop.assert_called_once()
        with pytest.raises(InferenceUnavailable):
            await loop.run_episode(state, controller)
        controller.turn.assert_called_once()

    asyncio.run(run())


def test_unusable_low_and_high_views_stop_before_chassis_motion(scan_loop):
    controller, _, model, _ = scan_loop
    state = RobotState(current_goal="Explore")
    model.return_value = decision(None, {}, target_visible=False, world_observation=semantic(quality="poor"))

    async def run():
        await loop.run_episode(state, controller)
        await loop.run_episode(state, controller)
        with pytest.raises(InferenceUnavailable, match="CAMERA_LOW_HEIGHT_MM"):
            await loop.run_episode(state, controller)

    asyncio.run(run())
    assert [obs["camera_height"] for obs in state.world_state.observations] == ["LOW", "HIGH"]
    controller.turn.assert_not_called()
    controller.stop.assert_called_once()


def test_camera_offsets_are_configurable_and_raise_failure_cannot_start_scanning(scan_loop, monkeypatch):
    controller, _, _, _ = scan_loop
    monkeypatch.setattr(loop, "CAMERA_SCAN_X_MM", 20)
    monkeypatch.setattr(loop, "CAMERA_SCAN_HEIGHTS_MM", {"LOW": 40, "HIGH": 70})
    state = RobotState(current_goal="Explore")

    async def run():
        await loop.run_episode(state, controller)
        controller.move_arm.assert_called_once_with(x_mm=20, y_mm=40)
        controller.move_arm.side_effect = RoboMasterError("arm stalled")
        with pytest.raises(InferenceUnavailable, match="HIGH positioning failed"):
            await loop.run_episode(state, controller)

    asyncio.run(run())
    controller.move_arm.assert_called_with(x_mm=0, y_mm=30)
    assert state.world_state.robot["camera_height"] == "unknown"
    controller.turn.assert_not_called()
    controller.stop.assert_called_once()


def test_invalid_camera_offsets_are_rejected_before_homing(scan_loop, monkeypatch):
    controller, _, _, _ = scan_loop
    monkeypatch.setattr(loop, "CAMERA_SCAN_HEIGHTS_MM", {"LOW": 70, "HIGH": 40})
    with pytest.raises(ValueError, match="LOW < HIGH"):
        asyncio.run(loop.run_episode(RobotState(current_goal="Explore"), controller))
    controller.recenter_arm.assert_not_called()


def test_non_divisor_step_closes_revolution_without_reversing(scan_loop, monkeypatch):
    controller, _, _, _ = scan_loop
    monkeypatch.setattr(loop, "SCAN_STEP_DEG", 70)
    state = RobotState(current_goal="Explore")

    async def run():
        for _ in range(13):  # Initial posture, twelve observations and six turns.
            await loop.run_episode(state, controller)

    asyncio.run(run())
    assert state.world_state.searched_headings == [0, 70, 140, 210, 280, 350]
    assert controller.turn.call_args_list == [call(degrees=70)] * 5 + [call(degrees=10)]
    assert state.startup_scan_status == "completed" and state.world_state.robot["heading_deg"] == 0


@pytest.mark.parametrize("step", [0, -60, 360, float("nan"), True])
def test_invalid_scan_step_rejected_before_hardware(step, scan_loop, monkeypatch):
    controller, _, _, _ = scan_loop
    monkeypatch.setattr(loop, "SCAN_STEP_DEG", step)
    with pytest.raises(ValueError):
        asyncio.run(loop.run_episode(RobotState(current_goal="Explore"), controller))
    controller.recenter_arm.assert_not_called()
    controller.turn.assert_not_called()


def test_defaults_and_disabled_scan(setup_loop):
    assert config.STARTUP_SCAN_ENABLED and config.SCAN_STEP_DEG == 60
    assert config.CAMERA_SCAN_HEIGHTS_MM == {"LOW": 30, "HIGH": 60}
    controller, _, _, _ = setup_loop
    asyncio.run(loop.run_episode(RobotState(current_goal="Find a chair"), controller))
    controller.recenter_arm.assert_not_called()
    controller.turn.assert_called_once_with(degrees=45)
