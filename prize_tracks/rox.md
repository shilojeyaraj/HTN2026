# Rox — Best AI Agent

**Prize:** $10K first, $2K second. 2 winners. (Biggest cash on the board.)
**Scope:** an LLM-driven agent operating on real-world messy data (unstructured, incomplete, conflicting, noisy) that takes meaningful actions. Rewards data cleaning/validation, multi-source resolution, error handling, decision-making under uncertainty. Judged on technical complexity, creativity, handling messiness, practical utility.

---

## How the rover targets the Rox track

This track is **framing, not extra code** — the rover already is the agent the track asks for. The pitch is to make the messiness the rover handles visible to the judges.

### The agent operates on real-world messy data

The rover's inputs are genuinely noisy and incomplete:

- **Monocular depth is relative, not absolute.** `perception/camera.py` gets pseudo-detections from a laptop running Depth-Anything-V2-Small over Wi-Fi (`laptop/server.py`). The depth values are advisory, not trustworthy in meters — see `CAMERA_GAP.md`. The brain has to act on uncertain proximity, not clean distances.
- **Wi-Fi is unreliable at a hackathon.** The deliberative loop degrades gracefully: on any cloud failure the robot slows or stops safely and keeps running (`CLAUDE.md` section 10). The reflex loop has no network dependency at all.
- **Sensor reads can fail or be stale.** `brain/loop.py:34` wraps vision in a try/except that keeps the prior `scene_description` if the call fails, rather than crashing the episode.
- **Audio is ambiguous.** `get_audio` returns a dB level and an event kind (distress / hazard noise / voice) — the brain has to decide whether a sound is a survivor calling for help or background noise, under uncertainty.
- **Speech transcription is imperfect.** The laptop runs faster-whisper (`laptop/audio.py`) locally on CPU with INT8 quantization and VAD filtering. Provisional transcripts are revised as more audio arrives; finals may contain errors. The `TranscriptBuffer` (`perception/transcript.py`) exposes both provisional and final events so the brain can act on partial information and revise.

### The agent takes meaningful actions

The brain doesn't just describe the scene — it drives. It calls `forward(0.5)`, the controller executes it, and the result (`completed` or `stopped_by_obstacle` with distance traveled) is fed back into the Backboard thread so the brain can react. That's the Inner Monologue pattern from the LLM-robotics literature, and it's the "takes meaningful actions" part of the scope.

### Decision-making under uncertainty

The two-loop architecture is the uncertainty handling:

- **Reflex loop (`control/reflex.py`)**: 30 Hz, classical, no cloud. If anything is within `STOP_DISTANCE_M = 0.3` ahead, it overrides the brain and stops. This is the error handling the track rewards — the agent can't drive into a wall even if the brain makes a bad call.
- **Safety gate (`brain/safety.py`)**: SayCan-style veto. Before `forward` reaches the arbiter, `safety.check` vetoes it if an obstacle is within `MIN_CLEARANCE_M = 0.4` in the forward arc. The brain proposes, feasibility gates it.
- **Arbiter (`control/arbiter.py`)**: priority mux. Reflex > brain > watchdog halt. If both go stale for `WATCHDOG_TIMEOUT_S = 0.5`, the robot halts. The agent fails safe.
- **Watchdog**: the base controller stops if no fresh command arrives within 0.5 s. If the software hangs, the robot halts instead of driving into a wall.

### Multi-source resolution — the occupancy map

The rover fuses **six sensor types** into a single 2D occupancy grid (`control/mapper.py`), each with different confidence levels:

| Sensor | Input | Confidence | How it's fused |
|---|---|---|---|
| Ultrasonic (HC-SR04) | Absolute distance + bearing | High | 3-ray Bresenham cone, log-odds +0.85 / -0.4 |
| Camera depth (Depth-Anything-V2) | Relative proximity 0-1 | Low | Ray-cast at 50% weight, skipped below 0.3 |
| Audio (mic + faster-whisper) | Speech transcripts, dB, event kind | Marker (no bearing) | Placed at rover position with label |
| Temperature (DHT22/DS18B20) | Celsius + status | Marker | Heat dome if warm/overheat |
| IMU (MPU6050) | Pitch, roll, yaw rate | Marker + pose | Hazard marker if tipped/bumped; yaw feeds dead-reckoning |
| Gemini vision | Scene description text | Annotation | Placed at rover position, geolocated text |

The log-odds grid handles conflicting readings naturally: if ultrasonic says "occupied" (high confidence) but depth says "free" (low confidence), the high-confidence reading dominates because it contributes a larger log-odds delta. That's multi-source resolution on conflicting noisy data, exactly the scope.

The map is built incrementally as the rover drives (`brain/loop.py:_update_map` runs after every episode), streamed to the frontend at 5 Hz via WebSocket (`control/map_server.py`), and rendered with overlay layers for each sensor type (`frontend/src/components/MapView.tsx`).

### Dead-reckoning under uncertainty

The `PoseEstimator` (`control/pose.py`) integrates gyro yaw rate + commanded velocity for position. It has ~0.25°/min yaw drift — the rover's position estimate degrades over time. The occupancy map is built on this imperfect pose, so the map itself is uncertain. The brain operates on a map that's built from noisy sensors on a drifting pose estimate — that's the messiness the track rewards.

---

## Integration points

| File | Role |
|---|---|
| `brain/loop.py` | The agent: perceive → plan → safety gate → execute → feed result back → update map |
| `brain/safety.py` | SayCan veto gate (uncertainty handling before action) |
| `control/reflex.py` | 30 Hz classical safety loop (error handling, no cloud) |
| `control/arbiter.py` | Priority mux + watchdog (fail-safe) |
| `control/mapper.py` | Occupancy grid: log-odds Bresenham ray-casting, 6 sensor overlay layers |
| `control/pose.py` | Dead-reckoning pose estimator (gyro + velocity integration) |
| `control/map_server.py` | WebSocket server streaming map at 5 Hz to frontend |
| `perception/transcript.py` | TranscriptBuffer: thread-safe bridge from STT to brain |
| `laptop/audio.py` | Local faster-whisper STT: VAD-gated, provisional + final transcripts |
| `perception/camera.py` | Noisy depth input source |
| `brain/tools.py` | The action space the agent chooses from |

---

## Demo narrative

"The rover is an AI agent acting on messy, incomplete sensor data under real uncertainty. Its depth comes from a monocular model over flaky Wi-Fi — it's advisory, not exact. Its audio is ambiguous. Its cloud brain can drop at any time. So it has a fast onboard safety loop that stops it at a wall with zero cloud involved, a SayCan-style gate that vetoes actions the scene says are unsafe, and a watchdog that halts it if anything goes stale. The brain proposes, the safety floor disallows, and the real result of every action goes back into the conversation so the agent can change its mind. Meanwhile, six sensor types — ultrasonic, monocular depth, microphone, temperature, IMU, and Gemini vision — are fused into a live occupancy map with log-odds confidence weighting, streamed to the operator in realtime. The map is built on a dead-reckoning pose estimate that drifts. That's an agent handling messiness at every layer, not a chatbot."

The strongest single-line pitch for this track: **the rover is an agent acting under uncertainty on noisy real-world data, fusing six sensor types into a live map with a safety floor that catches it when it's wrong** — which is the track's exact ask.
