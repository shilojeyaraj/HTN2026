"""Unit tests for the pose estimator and occupancy map accumulator."""

import base64
import math

import numpy as np

from control.mapper import OccupancyMap
from control.pose import PoseEstimator


class TestPoseEstimator:
    def test_starts_at_origin(self):
        pe = PoseEstimator()
        assert pe.pose == (0.0, 0.0, 0.0)

    def test_moves_forward(self):
        pe = PoseEstimator()
        pe.update(gyro_z_dps=0.0, linear_velocity=0.3, dt=1.0)
        assert abs(pe.x - 0.3) < 0.01
        assert abs(pe.y) < 0.01
        assert abs(pe.heading_rad) < 0.01

    def test_turns(self):
        pe = PoseEstimator()
        pe.update(gyro_z_dps=90.0, linear_velocity=0.0, dt=1.0)
        assert abs(math.degrees(pe.heading_rad) - 90.0) < 1.0

    def test_moves_in_arc(self):
        pe = PoseEstimator()
        pe.update(gyro_z_dps=90.0, linear_velocity=0.3, dt=1.0)
        assert pe.x > 0
        assert pe.y > 0

    def test_calibration_removes_bias(self):
        pe = PoseEstimator()
        pe.calibrate(lambda: 2.0)  # bias of 2 dps
        pe.update(gyro_z_dps=2.0, linear_velocity=0.0, dt=1.0)
        assert abs(pe.heading_rad) < 0.001  # bias removed, no rotation

    def test_pose_property_returns_degrees(self):
        pe = PoseEstimator()
        pe.update(gyro_z_dps=45.0, linear_velocity=0.0, dt=1.0)
        _, _, heading_deg = pe.pose
        assert abs(heading_deg - 45.0) < 1.0


class TestOccupancyMap:
    def test_grid_starts_unknown(self):
        m = OccupancyMap(size_m=4.0, resolution_m=0.2)
        assert m.grid.shape == (20, 20)
        assert np.all(m.grid == 0.0)

    def test_ultrasonic_marks_endpoint_occupied(self):
        m = OccupancyMap(size_m=4.0, resolution_m=0.2)
        pose = (0.0, 0.0, 0.0)
        m.add_ultrasonic(pose, bearing_deg=0, distance_m=1.0)
        prob = 1.0 / (1.0 + np.exp(-m.grid))
        # pose (0,0) maps to grid (10,10); endpoint 1m forward maps to (15,10)
        endpoint = prob[10, 15]
        assert endpoint > 0.5  # endpoint marked as likely occupied

    def test_ultrasonic_marks_ray_free(self):
        m = OccupancyMap(size_m=4.0, resolution_m=0.2)
        pose = (0.0, 0.0, 0.0)
        m.add_ultrasonic(pose, bearing_deg=0, distance_m=1.0)
        prob = 1.0 / (1.0 + np.exp(-m.grid))
        # A cell between origin and endpoint should be free
        free_cell = prob[10, 12]  # a few cells forward of center
        assert free_cell < 0.5

    def test_depth_low_confidence(self):
        m = OccupancyMap(size_m=10.0, resolution_m=0.2)
        pose = (0.0, 0.0, 0.0)
        m.add_depth(pose, bearing_deg=0, proximity=0.5)  # distance = 1.5m
        prob = 1.0 / (1.0 + np.exp(-m.grid))
        # pose (0,0) maps to grid (25,25); endpoint 1.5m forward maps to (25,32)
        endpoint = prob[25, 32]
        assert endpoint > 0.5

    def test_depth_skips_low_proximity(self):
        m = OccupancyMap(size_m=4.0, resolution_m=0.2)
        pose = (0.0, 0.0, 0.0)
        m.add_depth(pose, bearing_deg=0, proximity=0.1)
        assert np.all(m.grid == 0.0)  # nothing written

    def test_sound_marker_at_rover_position(self):
        m = OccupancyMap(size_m=4.0, resolution_m=0.2)
        m.add_sound((1.0, 0.5, 30.0), kind="distress", label="voice", db=68.0)
        assert len(m.sound_sources) == 1
        assert m.sound_sources[0]["x"] == 1.0
        assert m.sound_sources[0]["y"] == 0.5
        assert m.sound_sources[0]["kind"] == "distress"

    def test_heat_skips_ok_status(self):
        m = OccupancyMap(size_m=4.0, resolution_m=0.2)
        m.add_heat((0.0, 0.0, 0.0), celsius=22.0, status="ok")
        assert len(m.heat_points) == 0

    def test_heat_adds_warm(self):
        m = OccupancyMap(size_m=4.0, resolution_m=0.2)
        m.add_heat((0.0, 0.0, 0.0), celsius=48.0, status="warm")
        assert len(m.heat_points) == 1
        assert m.heat_points[0]["celsius"] == 48.0

    def test_hazard_marker(self):
        m = OccupancyMap(size_m=4.0, resolution_m=0.2)
        m.add_hazard((1.0, 1.0, 0.0), "bump")
        assert len(m.hazards) == 1
        assert m.hazards[0]["type"] == "bump"

    def test_annotation(self):
        m = OccupancyMap(size_m=4.0, resolution_m=0.2)
        m.add_annotation((2.0, 1.0, 0.0), "collapsed ceiling", "gemini")
        assert len(m.annotations) == 1
        assert m.annotations[0]["text"] == "collapsed ceiling"

    def test_trail_capped(self):
        m = OccupancyMap(size_m=4.0, resolution_m=0.2)
        for i in range(600):
            m.add_trail((float(i), 0.0, 0.0))
        assert len(m.trail) == 500

    def test_to_payload_shape(self):
        m = OccupancyMap(size_m=4.0, resolution_m=0.2)
        m.add_ultrasonic((0.0, 0.0, 0.0), 0, 1.0)
        m.add_sound((0.0, 0.0, 0.0), "voice", "hello", 60.0)
        payload = m.to_payload((0.0, 0.0, 45.0))
        assert payload["grid_width"] == 20
        assert payload["grid_height"] == 20
        assert payload["grid_encoding"] == "base64_uint8"
        grid_bytes = base64.b64decode(payload["grid"])
        assert len(grid_bytes) == 400
        assert payload["rover_pose"] == [0.0, 0.0, 45.0]
        assert len(payload["sound_sources"]) == 1
        assert payload["trail"] == []

    def test_world_to_grid_centered(self):
        m = OccupancyMap(size_m=4.0, resolution_m=0.2)
        gx, gy = m._world_to_grid(0.0, 0.0)
        assert gx == 10
        assert gy == 10

    def test_add_transcript_marker(self):
        m = OccupancyMap(size_m=4.0, resolution_m=0.2)
        m.add_transcript((1.0, 0.5, 0.0), "forward 2 meters", final=True)
        m.add_transcript((1.2, 0.6, 0.0), "turn left", final=False)
        assert len(m.sound_sources) == 2
        assert m.sound_sources[0]["kind"] == "speech"
        assert m.sound_sources[0]["label"] == "forward 2 meters"
        assert m.sound_sources[0]["final"] is True
        assert m.sound_sources[1]["final"] is False


class TestTranscriptBuffer:
    def test_push_and_consume_final(self):
        from perception.transcript import TranscriptBuffer
        buf = TranscriptBuffer()
        buf.push("hello", final=False, utterance_id=1)
        assert buf.consume_final() is None
        buf.push("hello world", final=True, utterance_id=1)
        assert buf.consume_final() == "hello world"
        assert buf.consume_final() is None

    def test_recent_returns_both_partial_and_final(self):
        from perception.transcript import TranscriptBuffer
        buf = TranscriptBuffer()
        buf.push("hey", final=False, utterance_id=1)
        buf.push("hey there", final=True, utterance_id=1)
        buf.push("next", final=False, utterance_id=2)
        recent = buf.recent(5)
        assert len(recent) == 3
        assert recent[0].text == "hey"
        assert recent[1].final is True
        assert recent[2].utterance_id == 2

    def test_overwrites_latest_final(self):
        from perception.transcript import TranscriptBuffer
        buf = TranscriptBuffer()
        buf.push("first", final=True, utterance_id=1)
        buf.push("second", final=True, utterance_id=2)
        assert buf.consume_final() == "second"
        assert buf.consume_final() is None
