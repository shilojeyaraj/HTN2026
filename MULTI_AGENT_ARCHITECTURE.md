# Multi-Agent System Architecture

## System Overview

The rover is a heterogeneous multi-agent system for autonomous rescue operations. Seven agents with distinct roles, models, and execution environments coordinate through shared state, a transcript buffer, a priority arbiter, and a live occupancy map. The system runs on two machines: a Raspberry Pi 5 (rover) and a laptop (perception + STT), connected over Wi-Fi.

---

## Agents

### 1. STT Agent — Speech-to-Text
- **Model:** faster-whisper `base.en` (CTranslate2 INT8)
- **Location:** Laptop CPU
- **Role:** Always-on speech transcription from the rover's microphone
- **Input:** 16kHz mono PCM audio streamed from Pi over TCP (interleaved with video)
- **Output:** Transcript events `{text, final, utterance_id}` — provisional during speech, final after 0.7s silence
- **Key feature:** VAD-gated (RMS threshold), no cloud dependency, provisional transcripts revised as more audio arrives
- **File:** `laptop/audio.py`

### 2. Parser Agent — Command Parser
- **Model:** Qwen3-1.7B LoRA fine-tune (checkpoint-105, served by vLLM on Baseten H100)
- **Location:** Baseten cloud (OpenAI-compatible `/v1/chat/completions` endpoint)
- **Role:** Parse natural-language voice commands into structured verb calls
- **Input:** Transcript text string
- **Output:** `{"verb": "forward", "args": {"distance_m": 2.0}}` or `None` if unrecognized
- **Key feature:** Fast-path — simple commands execute directly without a Backboard round-trip. Falls through to the Planner Agent if unrecognized.
- **File:** `brain/command_parser.py`

### 3. Vision Agent — Scene Understanding
- **Model:** Gemini 2.5 Flash (routed through Backboard as BYOK)
- **Location:** Backboard cloud (our Gemini API key connected in Backboard dashboard)
- **Role:** Describe the camera frame: notable objects, free space, hazards
- **Input:** JPEG frame + depth detections
- **Output:** 2-3 sentence scene description → `state.scene_description`
- **Key feature:** Scene descriptions are geolocated onto the occupancy map as annotations
- **File:** `perception/vision.py`, `brain/backboard_client.py`

### 4. Planner Agent — Deliberative Reasoning
- **Model:** Gemini 2.5 Pro (routed through Backboard as BYOK)
- **Location:** Backboard cloud (same thread as Vision Agent)
- **Role:** Reason over scene + goal + user command, call motion verbs, handle sensor reads
- **Input:** Scene description, current goal, user command, robot pose
- **Output:** Tool calls (forward, backward, turn, stop, speak, get_obstacles, get_state, get_temperature, get_audio, get_gyro)
- **Key feature:** Inner Monologue — real execution results fed back into the same Backboard thread. Memory="Auto" retains mission context across episodes.
- **File:** `brain/backboard_client.py`, `brain/loop.py`

### 5. Safety Agent — Veto Gate
- **Model:** Classical (no LLM)
- **Location:** Pi (onboard)
- **Role:** SayCan-style veto — block actions the scene says are unsafe
- **Input:** Planned verb + latest detections
- **Output:** `OK` or `VETO`
- **Key feature:** Only `forward` is gated (other verbs are inherently safe). Veto returns `{"status": "vetoed", "reason": "obstacle ahead"}` to the Planner.
- **File:** `brain/safety.py`

### 6. Reflex Agent — Emergency Safety Loop
- **Model:** Classical (no LLM, no cloud)
- **Location:** Pi (onboard, 30 Hz)
- **Role:** Emergency stop and obstacle avoidance with final authority over motor commands
- **Input:** Latest detections from camera/ultrasonic
- **Output:** Override `cmd_vel` (zero speed) when obstacle within 0.3m, or `None` (let brain through)
- **Key feature:** Runs at 30 Hz independent of the brain. Wins at the arbiter. Also updates the Pose Agent every tick. Network-independent — keeps the rover safe even if all cloud calls fail.
- **File:** `control/reflex.py`

### 7. Mapper Agent — Spatial Fusion
- **Model:** Classical (numpy, no LLM)
- **Location:** Pi (onboard)
- **Role:** Fuse six sensor types into a 2D occupancy grid with log-odds confidence
- **Input:** Ultrasonic distances, camera depth proximity, audio events, temperature, IMU readings, Gemini scene descriptions
- **Output:** Occupancy grid + overlay layers (sound markers, heat points, hazards, annotations, trail) → serialized to JSON → WebSocket at 5 Hz → frontend
- **Key feature:** Log-odds Bresenham ray-casting handles conflicting sensor readings with different confidence weights. High-confidence ultrasonic dominates low-confidence depth.
- **File:** `control/mapper.py`, `control/map_server.py`

### Supporting: Pose Agent
- **Model:** Classical (complementary filter on MPU6050)
- **Location:** Pi (onboard, updated at 30 Hz by Reflex Agent)
- **Role:** Dead-reckoning position tracking
- **Input:** Gyro yaw rate + commanded linear velocity
- **Output:** `(x, y, heading_deg)` pose tuple
- **File:** `control/pose.py`

### Supporting: TTS Agent
- **Model:** ElevenLabs `eleven_flash_v2_5` (~75ms latency)
- **Location:** Cloud (direct SDK call, not routed through Backboard)
- **Role:** Voice output — the rover speaks
- **Input:** Text string from Planner's `speak()` tool call
- **Output:** Audio played on speaker (async, daemon thread, never blocks control loop)
- **File:** `voice/tts.py`

---

## Communication Channels

| Channel | From → To | Mechanism | Data |
|---|---|---|---|
| TCP A/V stream | Pi → Laptop | FFmpeg V4L2 + ALSA → TCP socket | MJPEG video + 16kHz PCM audio (interleaved, `PCM1` prefix) |
| Depth results | Laptop → Pi | TCP downstream JSON | `{status, relative_proximity, preferred_direction}` |
| Transcript downstream | Laptop → Pi | TCP downstream JSON (piggybacked on depth results) | `{text, utterance_id}` final transcripts |
| TranscriptBuffer | STT Agent → Planner/Parser | Thread-safe queue (`perception/transcript.py`) | `consume_final()` returns latest final transcript string |
| RobotState | All brain agents | Shared dataclass (`brain/state.py`) | `scene_description`, `detections`, `current_goal`, `last_user_command`, `safety_status`, `robot_pose`, `velocity` |
| Backboard thread | Vision ↔ Planner | Same Backboard thread, different model routing | Vision output (scene description) becomes Planner input |
| Arbiter | Reflex + Planner → Motors | Priority mux (`control/arbiter.py`) | Reflex (high priority) overrides Planner (low priority); watchdog halts if both stale for 0.5s |
| WebSocket | Mapper → Frontend | `websockets` library at 5 Hz (`control/map_server.py`) | Full map payload: grid + overlays + rover pose + trail |
| Tool results | Controller → Planner | `submit_tool_outputs_simple` (Backboard SDK) | Real execution results: `completed`, `stopped_by_obstacle`, sensor readings |

---

## Two-Loop Architecture

### Fast Loop (30 Hz, onboard, classical, no cloud)

```
Reflex Agent (30 Hz)
  ├── Read detections (camera/ultrasonic)
  ├── If obstacle within 0.3m → override cmd_vel to (0, 0)
  ├── Else → let brain's command through
  └── Update Pose Agent every tick
       └── Integrate gyro yaw + velocity → (x, y, heading)

Arbiter
  ├── Reflex cmd (high priority) → wins if active
  ├── Brain cmd (low priority) → passes if reflex is idle
  └── Watchdog → halt if no command for 0.5s
```

### Slow Loop (~1 Hz, cloud, deliberative)

```
Brain Episode (brain/loop.py)
  1. PERCEIVE
     └── Vision Agent: frame → Gemini Flash → scene_description

  2. CHECK TRANSCRIPTS
     └── TranscriptBuffer.consume_final() → state.last_user_command

  3. PARSE (fast path)
     └── Parser Agent: command → Qwen3 LoRA → verb call
     └── If recognized → execute directly, skip Backboard
     └── If unrecognized → fall through to Planner

  4. PLAN (Backboard brain)
     └── Planner Agent: scene + goal + command → Gemini Pro → tool calls
     └── For each tool call:
         a. Safety Agent: check verb against detections → OK or VETO
         b. Execute verb (forward/turn/stop/speak/sensor read)
         c. Feed real result back to Backboard (Inner Monologue)
     └── Loop up to 6 rounds

  5. UPDATE MAP
     └── Mapper Agent: fuse all sensors → occupancy grid + overlays
     └── WebSocket stream to frontend at 5 Hz
```

---

## Data Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        RASPBERRY PI 5                                │
│                                                                      │
│  ┌──────────┐    FFmpeg     ┌──────────────┐                         │
│  │ USB Webcam│──V4L2──────→│              │                         │
│  │ + Mic     │──ALSA──────→│  pi/client.py│──── TCP ──────────────┐ │
│  └──────────┘             └──────────────┘                        │ │
│                                                           │       │ │
│  ┌─────────────┐     ┌─────────────┐                      │       │ │
│  │ Reflex Agent│────→│   Arbiter   │──→ cmd_vel ──→ Motors│       │ │
│  │ (30 Hz)     │     │ (priority   │                      │       │ │
│  └──────┬──────┘     │  mux)       │                      │       │ │
│         │            └──────▲──────┘                      │       │ │
│         │                   │ brain cmd                    │       │ │
│         v                   │                              │       │ │
│  ┌─────────────┐     ┌──────┴──────┐                      │       │ │
│  │ Pose Agent  │     │ brain/loop.py│                      │       │ │
│  │ (dead-reckon)│    │ (episode)   │                      │       │ │
│  └──────┬──────┘     └──────┬──────┘                      │       │ │
│         │                   │                              │       │ │
│         │            ┌──────┴──────┐                      │       │ │
│         │            │ Safety Agent │                      │       │ │
│         │            │ (SayCan veto)│                      │       │ │
│         │            └──────┬──────┘                      │       │ │
│         │                   │                              │       │ │
│         v                   v                              v       │ │
│  ┌─────────────┐     ┌─────────────┐               ┌──────────────┐ │ │
│  │ Mapper Agent│←───│ Controller  │               │  Map Server  │ │ │
│  │ (occupancy  │     │ (verb →     │               │  (WebSocket)  │ │ │
│  │  grid)      │     │  cmd_vel)   │               └──────┬───────┘ │ │
│  └──────┬──────┘     └─────────────┘                      │       │ │
│         │                                            ws://0.0.0.0:8766
│         │                                                   │       │ │
└─────────┼───────────────────────────────────────────────────┼───────┘ │
          │                                                   │         │
          │              ┌────────────────────────────────────┘         │
          │              v                                              │
          │     ┌────────────────┐    ┌──────────────────┐             │
          │     │   FRONTEND     │    │     LAPTOP        │             │
          │     │  (React)       │    │                   │             │
          │     │  MapView.tsx   │←──│  laptop/server.py │←──TCP──────┘
          │     │  (canvas 2D)   │    │  (depth + STT)    │
          │     └────────────────┘    └──────┬───────────┘
          │                                 │
          │                          ┌──────┴──────┐
          │                          │ STT Agent   │
          │                          │ faster-     │
          └──────────────────────────│ whisper     │
                                     │ (local CPU)  │
                                     └──────┬──────┘
                                            │
                                     transcript text
                                            │
                                     ┌──────v──────┐
                                     │ Transcript  │
                                     │ Buffer      │
                                     │ (thread-    │
                                     │  safe queue)│
                                     └─────────────┘
```

---

## Cloud Services (called directly, not through each other)

```
┌─────────────────────────────────────────────────────────────┐
│                    CLOUD SERVICES                           │
│                                                             │
│  ┌─────────────────┐  ┌──────────────┐  ┌────────────────┐  │
│  │   Backboard     │  │    Baseten   │  │   ElevenLabs   │  │
│  │   (brain API)   │  │   (inference)│  │   (TTS API)    │  │
│  │                 │  │              │  │                │  │
│  │ ┌─────────────┐ │  │ ┌──────────┐ │  │ ┌────────────┐ │  │
│  │ │Gemini Flash │ │  │ │Qwen3 LoRA│ │  │ │eleven_flash│ │  │
│  │ │(vision)     │ │  │ │(parser)  │ │  │ │_v2_5      │ │  │
│  └─────────────┘ │  │ └──────────┘ │  │ └────────────┘ │  │
│  │ ┌─────────────┐ │  │ ┌──────────┐ │  └────────────────┘  │
│  │ │Gemini Pro   │ │  │ │Whisper   │ │                      │
│  │ │(planner)    │ │  │ │(fallback)│ │                      │
│  │ └─────────────┘ │  │ └──────────┘ │                      │
│  │  + Memory       │  │              │                      │
│  │  + Tool calling │  │              │                      │
│  └─────────────────┘  └──────────────┘                      │
└─────────────────────────────────────────────────────────────┘
```

---

## Key Scenarios (Sequence Flows)

### Scenario 1: Voice command "forward 2 meters"

```
1. Pi mic captures audio → FFmpeg ALSA → TCP → laptop
2. STT Agent (faster-whisper): audio → "forward 2 meters" (final transcript)
3. Transcript downstream: laptop → Pi (piggybacked on depth JSON)
4. Pi client: on_transcript callback → TranscriptBuffer.push()
5. Brain loop: TranscriptBuffer.consume_final() → state.last_user_command
6. Parser Agent: "forward 2 meters" → {"verb": "forward", "args": {"distance_m": 2.0}}
7. Safety Agent: check forward against detections → OK
8. Controller: forward(2.0) → cmd_vel → arbiter → motors
9. Reflex Agent (30 Hz): monitors clearance during execution
10. Result: {"status": "completed", "distance_traveled": 2.0}
11. Mapper Agent: update trail + sensor readings → WebSocket → frontend
```

### Scenario 2: Obstacle detected during forward motion

```
1. Reflex Agent (30 Hz): reads detections → obstacle within 0.3m
2. Reflex Agent: sets reflex_cmd = (0.0, 0.0) → arbiter overrides brain
3. Arbiter: outputs (0.0, 0.0) → motors stop
4. Brain episode: forward() returns {"status": "stopped_by_obstacle", "distance_traveled": 0.7}
5. Planner Agent (Backboard): receives "stopped_by_obstacle" via Inner Monologue
6. Planner Agent: decides to turn → calls turn(50)
7. Safety Agent: turn is not gated → OK
8. Controller: turn(50) → cmd_vel → arbiter → motors
9. Mapper Agent: ray-casts obstacle onto grid (occupied cells)
```

### Scenario 3: Distress call heard

```
1. STT Agent: transcribes "help me" → TranscriptBuffer
2. Brain loop: consume_final() → state.last_user_command = "help me"
3. Parser Agent: "help me" → None (not a simple verb command)
4. Planner Agent (Backboard): receives "help me" as user command
5. Planner Agent: calls speak("I hear you, I'm coming") + forward(1.0)
6. TTS Agent (ElevenLabs): "I hear you, I'm coming" → speaker (async)
7. Mapper Agent: add_transcript(pose, "help me", final=True) → speech marker on map
8. Mapper Agent: add_sound(pose, "distress", "help me", 85) → sound marker on map
9. Frontend: displays distress soundwave + speech marker at rover position
```

### Scenario 4: Cloud failure (graceful degradation)

```
1. Wi-Fi drops → Backboard, Gemini, Baseten, ElevenLabs all fail
2. Reflex Agent (30 Hz): continues running (no cloud dependency)
3. Reflex Agent: monitors obstacles, stops at walls, keeps rover safe
4. Pose Agent: continues dead-reckoning (no cloud dependency)
5. Mapper Agent: continues building map from onboard sensors (no cloud)
6. Brain loop: try/except catches cloud failures, keeps prior scene_description
7. Arbiter: watchdog halts if no brain command for 0.5s, reflex still active
8. Rover: safe but silent — drives by reflex only, no deliberation
```

---

## Agent Coordination Summary

| Coordination Type | Example |
|---|---|
| **Sequential pipeline** | STT → Parser → Safety → Controller → Motors |
| **Shared state** | All brain agents read/write `RobotState` |
| **Priority override** | Reflex Agent overrides Planner at the Arbiter |
| **Feedback loop** | Controller results → Backboard thread (Inner Monologue) |
| **Spatial sharing** | All sensor agents → Mapper Agent → shared occupancy map |
| **Model routing** | Vision (Flash) and Planner (Pro) share one Backboard thread |
| **Fast-path shortcut** | Parser Agent can skip the Planner entirely for simple commands |
| **Veto gate** | Safety Agent can block Planner's proposed action |
| **Watchdog** | Arbiter halts if both Reflex and Brain go stale |
