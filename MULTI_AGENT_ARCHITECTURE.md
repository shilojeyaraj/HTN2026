# Multi-Agent System Architecture

## Virtual Demo Mode

When hardware is unavailable, the system runs as a **browser-based 3D virtual rescue simulation**. The real Backboard brain (gemini-3-flash-preview) drives a simulated rover through a 3D disaster environment via `frontend/virtual_brain_server.py`. The brain calls real tools, retrieves RAG protocols, speaks via ElevenLabs TTS, logs to MongoDB, and builds a progressive LiDAR occupancy map — all in the browser, no hardware needed.

**Virtual mode components:**
- `frontend/virtual_brain_server.py` — real Backboard brain + SimRover + WebSocket streaming (port 8766)
- `frontend/src/components/DrivingView3D.tsx` — 3D driving view with rover, people, buildings, terrain
- `frontend/src/components/MappingView3D.tsx` — 3D occupancy map with progressive LiDAR + detection captions
- `frontend/src/components/AINarrative.tsx` — AI mission summary with alerts and pattern analysis
- `frontend/src/components/RatingPanel.tsx` — TTS thumbs up/down evaluation for human feedback
- `training/scenario_generator.py` — disaster scenario generator with messy sensor data
- `training/collect_traces.py` — brain trace collector + evaluator
- `training/train_rescue.py` — SFT dataset converter for Baseten fine-tuning

**Note:** The planner model is `gemini-3-flash-preview` (not gemini-2.5-pro, which is deprecated; not gemini-3.5-flash, which hits free-tier quota limits).

---

## System Overview

The rover is a heterogeneous multi-agent system for autonomous rescue operations. Nine agents — 1 Leader + 8 Teammates — with distinct roles, models, and execution environments coordinate through shared state, a transcript buffer, a priority arbiter, a live occupancy map, and a Backboard RAG/memory layer. The system runs across three machines: a Raspberry Pi 5 (rover), a laptop (perception + STT), and the cloud (Backboard, Baseten, ElevenLabs).

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                              INPUTS (SENSORS)                                     │
│                                                                                   │
│  USB Webcam    USB Mic    Temp Sensor    IMU/MPU6050    Speaker    Push Button    │
│  (MJPEG 15fps) (16kHz PCM) (DHT22/DS18B20) (gyro+accel)  (playback)  (GPIO 17)    │
└──────┬───────────┬──────────┬────────────┬───────────┬──────────┬──────────────┘
       │           │          │            │           │          │
       ▼           ▼          │            │           │          │
┌──────────────────────────┐  │            │           │          │
│     RASPBERRY PI 5       │  │            │           │          │
│                          │  │            │           │          │
│  ┌─────────────────────┐ │  │            │           │          │
│  │  pi/client.py       │ │  │            │           │          │
│  │  FFmpeg V4L2 + ALSA │ │  │            │           │          │
│  │  → TCP stream       │──┼──┼───────────┼───────────┼──────────┘
│  └─────────────────────┘ │  │            │           │
│                          │  │            │           │
│  ┌─────────────────────┐ │  │            │           │
│  │  REFLEX AGENT       │ │  │            │           │
│  │  (30 Hz, classical) │ │  │            │           │
│  │  Reads camera depth  │ │  │            │           │
│  │  → emergency stop    │ │  │            │           │
│  │  → override cmd_vel  │ │  │            │           │
│  └────────┬────────────┘ │  │            │           │
│           │               │  │            │           │
│           ▼               │  │            │           │
│  ┌─────────────────────┐ │  │            │           │
│  │  ARBITER            │ │  │            │           │
│  │  (priority mux)     │ │  │            │           │
│  │  reflex > brain     │ │  │            │           │
│  │  watchdog 0.5s halt │ │  │            │           │
│  └────────┬────────────┘ │  │            │           │
│           │               │  │            │           │
│           ▼               │  │            │           │
│  ┌─────────────────────┐ │  │            │           │
│  │  MOTOR DRIVER       │ │  │            │           │
│  │  (control/motors.py)│ │  │            │           │
│  │  cmd_vel → PWM      │ │  │            │           │
│  └─────────────────────┘ │  │            │           │
│                          │  │            │           │
│  ┌─────────────────────┐ │  │            │           │
│  │  POSE AGENT         │ │  │            │           │
│  │  (complementary     │←─┼──┘            │           │
│  │   filter, 30 Hz)    │  │              │           │
│  │  gyro + velocity    │  │              │           │
│  │  → (x, y, heading)  │  │              │           │
│  └────────┬───────────┘  │              │           │
│           │               │              │           │
│  ┌────────▼───────────┐   │              │           │
│  │  MAPPER AGENT      │   │              │           │
│  │  (occupancy grid)   │←──┘              │           │
│  │  5 sensor types:    │                  │           │
│  │  • camera depth     │                  │           │
│  │  • audio events     │←─────────────────┘           │
│  │  • temperature      │←──────────────────┘         │
│  │  • IMU hazards      │←───────────────────┘       │
│  │  • Gemini annot.    │←─────────────────────┘     │
│  │  → log-odds grid    │                              │
│  │  → overlay layers   │                              │
│  └────────┬───────────┘                              │
│           │                                           │
│  ┌────────▼───────────┐                              │
│  │  MAP SERVER        │                              │
│  │  (WebSocket 5 Hz)  │                              │
│  │  ws://0.0.0.0:8766 │                              │
│  └────────┬───────────┘                              │
└───────────┼──────────────────────────────────────────┘
            │
            │ ws://
            ▼
┌──────────────────────────────────────────────────────┐
│  FRONTEND (React + Three.js)                         │
│                                                      │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐      │
│  │ CameraFeed │  │  MapView   │  │ Transcript │      │
│  │ (live MJPEG)│  │ (3D scene) │  │ (STT text) │      │
│  └────────────┘  └────────────┘  └────────────┘      │
│  ┌────────────────────────────────────────────┐      │
│  │ CurrentEncounter (status, sector, duration) │      │
│  └────────────────────────────────────────────┘      │
└──────────────────────────────────────────────────────┘

           ┌─────────────────────────────────────────────────────────────┐
           │                    CLOUD (SLOW LOOP ~1 Hz)                    │
           │                                                             │
           │  ┌─────────────────────────────────────────────────────┐     │
           │  │              BACKBOARD (Brain API)                    │     │
           │  │                                                       │     │
           │  │  ┌──────────────────────────────────────────────┐    │     │
           │  │  │         LEADER: Planner Agent                 │    │     │
           │  │  │         (Gemini 2.5 Pro, BYOK)                 │    │     │
           │  │  │                                              │    │     │
           │  │  │  Receives: scene + goal + command + pose      │    │     │
           │  │  │  Calls 16 tools:                             │    │     │
           │  │  │  ┌──────────────────────────────────────┐    │    │     │
           │  │  │  │ MOTION TOOLS                         │    │    │     │
           │  │  │  │  forward(distance_m)                  │    │    │     │
           │  │  │  │  backward(distance_m)                 │    │    │     │
           │  │  │  │  turn(degrees)                        │    │    │     │
           │  │  │  │  stop()                               │    │    │     │
           │  │  │  │  speak(text) → ElevenLabs TTS         │    │    │     │
           │  │  │  │  get_obstacles()                      │    │    │     │
           │  │  │  │  get_state()                          │    │    │     │
           │  │  │  │  get_temperature()                    │    │    │     │
           │  │  │  │  get_audio()                          │    │    │     │
           │  │  │  │  get_gyro()                           │    │    │     │
           │  │  │  ├──────────────────────────────────────┤    │    │     │
           │  │  │  │ TEAMMATE TOOLS                        │    │    │     │
           │  │  │  │  look_around() → Vision Agent (Flash)│    │    │     │
           │  │  │  │  check_map(radius_m) → Mapper Agent │    │    │     │
           │  │  │  │  check_safety(action) → Safety Agent│    │    │     │
           │  │  │  ├──────────────────────────────────────┤    │    │     │
           │  │  │  │ KNOWLEDGE TOOLS                      │    │    │     │
           │  │  │  │  search_knowledge(query) → RAG+mem  │    │    │     │
           │  │  │  │  log_finding(type, desc) → memory    │    │    │     │
           │  │  │  │  analyze_patterns() → insights       │    │    │     │
           │  │  │  └──────────────────────────────────────┘    │    │     │
           │  │  │                                              │    │     │
           │  │  │  Inner Monologue: real results fed back      │    │     │
           │  │  │  Memory="Auto": conversation across episodes  │    │     │
           │  │  │  MAX_TOOL_ROUNDS = 6                         │    │     │
           │  │  └──────────────────────────────────────────────┘    │     │
           │  │                                                       │     │
           │  │  ┌──────────────────────────────────────────────┐    │     │
           │  │  │  RAG KNOWLEDGE BASE                           │    │     │
           │  │  │  (uploaded via upload_document_to_assistant)  │    │     │
           │  │  │  • rescue_protocols.md (7 protocol categories)│    │     │
           │  │  │  • encounter_history.md (8 past encounters)   │    │     │
           │  │  │  Auto-retrieved when brain encounters matches │    │     │
           │  │  └──────────────────────────────────────────────┘    │     │
           │  │                                                       │     │
           │  │  ┌──────────────────────────────────────────────┐    │     │
           │  │  │  STRUCTURED MISSION MEMORY                    │    │     │
           │  │  │  (add_memory + search_memories)              │    │     │
           │  │  │  • 8 pre-loaded encounters (ENC-0140–0147)   │    │     │
           │  │  │  • Live findings (survivors, hazards)        │    │     │
           │  │  │  • get_memory_insights → pattern analysis    │    │     │
           │  │  └──────────────────────────────────────────────┘    │     │
           │  └─────────────────────────────────────────────────────┘     │
           │                                                             │
           │  ┌──────────────────┐  ┌──────────────────────────────┐      │
           │  │    BASETEN       │  │       ELEVENLABS             │      │
           │  │  (inference)     │  │       (TTS API)              │      │
           │  │                  │  │                              │      │
           │  │ ┌──────────────┐ │  │ ┌──────────────────────────┐ │      │
           │  │ │ Qwen3 LoRA   │ │  │ │ eleven_flash_v2_5       │ │      │
           │  │ │ (parser)     │ │  │ │ (~75ms latency)         │ │      │
           │  │ │ checkpoint-  │ │  │ │ async, daemon thread    │ │      │
           │  │ │ 105         │ │  │ │ never blocks control loop│ │      │
           │  │ └──────────────┘ │  │ └──────────────────────────┘ │      │
           │  │ ┌──────────────┐ │  └──────────────────────────────┘      │
           │  │ │ Whisper      │ │                                         │
           │  │ │ (fallback    │ │                                         │
           │  │ │  STT)        │ │                                         │
           │  │ └──────────────┘ │                                         │
           │  └──────────────────┘                                         │
           └─────────────────────────────────────────────────────────────┘

                    ┌─────────────────────────────────────────┐
                    │           LAPTOP (perception)            │
                    │                                         │
                    │  ┌──────────────────────────────────┐   │
                    │  │  STT AGENT                        │   │
                    │  │  faster-whisper base.en (INT8)    │   │
                    │  │  VAD-gated, local CPU             │   │
                    │  │  → provisional + final transcripts │   │
                    │  └──────────────┬───────────────────┘   │
                    │                 │                        │
                    │  ┌──────────────▼───────────────────┐   │
                    │  │  DEPTH SERVER                    │   │
                    │  │  Depth-Anything-V2-Small         │   │
                    │  │  → relative_proximity scores     │   │
                    │  │  → transcripts piggybacked       │   │
                    │  │    on downstream JSON            │   │
                    │  └──────────────┬───────────────────┘   │
                    │                 │                        │
                    │         TCP downstream JSON               │
                    │                 │                        │
                    │  ┌──────────────▼───────────────────┐   │
                    │  │  TranscriptBuffer                │   │
                    │  │  (thread-safe queue)              │   │
                    │  │  consume_final() → brain loop     │   │
                    │  └──────────────────────────────────┘   │
                    └─────────────────────────────────────────┘
```

---

## The 9 Agents

### LEADER: Planner Agent
- **Model:** Gemini 2.5 Pro (Backboard BYOK)
- **Location:** Cloud (Backboard)
- **Role:** Receives scene + goal + command + pose, reasons about what to do, calls 16 tools, coordinates teammates, consolidates results via Inner Monologue
- **Tools called:** All 16 verbs (motion, sensor, teammate, knowledge)
- **Memory:** `memory="Auto"` (conversation) + `add_memory`/`search_memories` (structured) + `get_memory_insights` (pattern analysis)
- **RAG:** 2 documents auto-retrieved (rescue protocols + encounter history)
- **File:** `brain/backboard_client.py`, `brain/loop.py`

### TEAMMATE 1: STT Agent
- **Model:** faster-whisper `base.en` (CTranslate2 INT8)
- **Location:** Laptop CPU
- **Input:** 16kHz mono PCM audio from Pi over TCP
- **Output:** Transcript events `{text, final, utterance_id}` → TranscriptBuffer
- **Reports to:** Planner (via TranscriptBuffer → `state.last_user_command`) and Parser (directly)
- **File:** `laptop/audio.py`

### TEAMMATE 2: Parser Agent
- **Model:** Qwen3-1.7B LoRA fine-tune (checkpoint-105, Baseten H100, vLLM)
- **Location:** Cloud (Baseten, OpenAI-compatible endpoint)
- **Input:** Transcript text string
- **Output:** `{"verb": "forward", "args": {"distance_m": 2.0}}` or `None`
- **Reports to:** Direct execution (bypasses Planner for simple commands)
- **File:** `brain/command_parser.py`

### TEAMMATE 3: Vision Agent
- **Model:** Gemini 2.5 Flash (Backboard BYOK, same thread as Planner)
- **Location:** Cloud (Backboard)
- **Input:** JPEG frame + depth detections
- **Output:** 2-3 sentence scene description → `state.scene_description`
- **Reports to:** Planner (via `state.scene_description`) and Mapper (as geolocated annotations)
- **Called by:** Planner's `look_around()` tool and automatically each episode in `_perceive()`
- **File:** `perception/vision.py`, `brain/backboard_client.py`

### TEAMMATE 4: Safety Agent
- **Model:** Classical (no LLM)
- **Location:** Pi (onboard)
- **Input:** Planned verb + latest detections
- **Output:** `OK` or `VETO`
- **Reports to:** Planner (returns veto status, Planner must react via Inner Monologue)
- **Called by:** Planner's `check_safety(action)` tool and automatically before each motion verb
- **File:** `brain/safety.py`

### TEAMMATE 5: Reflex Agent
- **Model:** Classical (no LLM, no cloud)
- **Location:** Pi (30 Hz, onboard)
- **Input:** Camera depth detections
- **Output:** Override `cmd_vel` (zero speed) when obstacle within 0.3m
- **Reports to:** Arbiter (overrides Planner at high priority)
- **Key feature:** Network-independent — keeps rover safe even if all cloud calls fail
- **File:** `control/reflex.py`

### TEAMMATE 6: Mapper Agent
- **Model:** Classical (numpy, no LLM)
- **Location:** Pi (onboard)
- **Input:** 5 sensor types: camera depth, audio events, temperature, IMU readings, Gemini annotations
- **Output:** Occupancy grid (log-odds) + overlay layers → WebSocket at 5 Hz → frontend
- **Reports to:** Planner (via `get_obstacles` and `check_map` tool) and Frontend (via WebSocket)
- **Called by:** Planner's `check_map(radius_m)` tool
- **File:** `control/mapper.py`, `control/map_server.py`

### SUPPORTING: Pose Agent
- **Model:** Classical (complementary filter on MPU6050)
- **Location:** Pi (30 Hz, updated by Reflex Agent)
- **Input:** Gyro yaw rate + commanded linear velocity
- **Output:** `(x, y, heading_deg)` pose tuple
- **Reports to:** Mapper (for map building) and Planner (via `get_state` tool)
- **File:** `control/pose.py`

### SUPPORTING: TTS Agent
- **Model:** ElevenLabs `eleven_flash_v2_5` (~75ms latency)
- **Location:** Cloud (direct SDK call)
- **Input:** Text string from Planner's `speak(text)` tool call
- **Output:** Audio on speaker (async, daemon thread, never blocks control loop)
- **Reports to:** Speaker (physical output to environment)
- **File:** `voice/tts.py`

---

## The 16 Tools (Leader's tool set)

### Motion Tools (5)
| Tool | Description | What happens |
|---|---|---|
| `forward(distance_m)` | Drive forward, then stop | Controller sets cmd_vel → arbiter → motors → returns `completed` or `stopped_by_obstacle` |
| `backward(distance_m)` | Drive backward, then stop | Same as forward, reverse direction |
| `turn(degrees)` | Turn in place, then stop | Controller sets angular velocity → arbiter → motors |
| `stop()` | Halt immediately | Controller sets cmd_vel = (0, 0) |
| `speak(text)` | Say something via TTS | ElevenLabs async call → speaker (never blocks) |

### Sensor Tools (5)
| Tool | Description | What happens |
|---|---|---|
| `get_obstacles()` | Read latest obstacle detections | Returns depth-based pseudo-detections |
| `get_state()` | Read robot pose, velocity, goal | Returns `(x, y, heading)` from Pose Agent |
| `get_temperature()` | Read ambient temperature | Returns `{celsius, status}` from temp sensor |
| `get_audio()` | Read microphone for sound events | Returns `{db, event: {kind, label}}` from mic |
| `get_gyro()` | Read IMU for tilt, impact | Returns `{pitch, roll, tipped, bump}` from MPU6050 |

### Teammate Tools (3)
| Tool | Teammate called | What happens |
|---|---|---|
| `look_around()` | Vision Agent (Gemini Flash) | Re-describes the current scene on demand |
| `check_map(radius_m)` | Mapper Agent | Returns nearby obstacles, sounds, heat, hazards, annotations |
| `check_safety(action)` | Safety Agent | Vets a proposed action → `OK` or `VETO` |

### Knowledge Tools (3)
| Tool | What happens |
|---|---|
| `search_knowledge(query)` | Searches RAG docs + structured memory via `search_memories` |
| `log_finding(type, desc)` | Stores a mission finding via `add_memory` with metadata |
| `analyze_patterns()` | Calls `get_memory_insights` for pattern analysis across all memory |

---

## Communication Channels

| Channel | From → To | Mechanism | Data |
|---|---|---|---|
| TCP A/V stream | Pi → Laptop | FFmpeg V4L2 + ALSA → TCP | MJPEG video + 16kHz PCM audio |
| Depth results | Laptop → Pi | TCP downstream JSON | `{status, relative_proximity, preferred_direction}` |
| Transcript downstream | Laptop → Pi | TCP JSON (piggybacked on depth) | `{text, utterance_id}` final transcripts |
| TranscriptBuffer | STT → Planner/Parser | Thread-safe queue | `consume_final()` → `state.last_user_command` |
| RobotState | All brain agents | Shared dataclass | `scene_description`, `detections`, `last_user_command`, `safety_status`, `robot_pose` |
| Backboard thread | Vision ↔ Planner | Same thread, model routing | Flash output becomes Pro input |
| Inner Monologue | Controller → Planner | `submit_tool_outputs_simple` | Real execution results: `completed`, `stopped_by_obstacle`, sensor readings |
| Arbiter | Reflex + Planner → Motors | Priority mux | Reflex (high) overrides Planner (low); watchdog halts if both stale 0.5s |
| WebSocket | Mapper → Frontend | `websockets` at 5 Hz | Full map payload: grid + overlays + pose + trail |
| RAG retrieval | Knowledge base → Planner | Auto-retrieval + `search_knowledge` tool | Rescue protocols, encounter records |
| Structured memory | Brain → Backboard | `add_memory` / `search_memories` | Mission findings with metadata |
| Memory insights | Backboard → Brain | `get_memory_insights` | Pattern analysis across all stored memory |

---

## Two-Loop Architecture

### Fast Loop (30 Hz, onboard, classical, no cloud)

```
Reflex Agent (30 Hz)
  ├── Read camera depth detections
  ├── If obstacle within 0.3m → set reflex_cmd = (0, 0)
  ├── Else → no override (let brain through)
  └── Update Pose Agent every tick
       └── Integrate gyro yaw + velocity → (x, y, heading)

Arbiter
  ├── Reflex cmd (high priority) → wins if active
  ├── Brain cmd (low priority) → passes if reflex idle
  └── Watchdog → halt if no command for 0.5s
```

### Slow Loop (~1 Hz, cloud, deliberative)

```
Brain Episode (brain/loop.py)
  1. PERCEIVE
     └── Vision Agent: frame → Gemini Flash → scene_description
     └── Scene geolocated onto map as annotation

  2. CHECK TRANSCRIPTS
     └── TranscriptBuffer.consume_final() → state.last_user_command

  3. PARSE (fast path)
     └── Parser Agent: command → Qwen3 LoRA → verb call
     └── If recognized → execute directly (skip Backboard)
     └── If unrecognized → fall through to Planner

  4. PLAN (Backboard brain — 16 tools, RAG, memory)
     └── Planner Agent: scene + goal + command → Gemini Pro → tool calls
     └── For each tool call (up to 6 rounds):
         a. Motion verb → Safety Agent checks → execute → Inner Monologue
         b. Sensor verb → read sensor → return data
         c. Teammate verb → call teammate → return result
         d. Knowledge verb → RAG/memory retrieval → return data
     └── Brain reacts to results (e.g. stopped_by_obstacle → turn)

  5. UPDATE MAP
     └── Mapper Agent: fuse 5 sensor types → occupancy grid + overlays
     └── WebSocket stream to frontend at 5 Hz
```

---

## Coordination Mechanisms

| Mechanism | How it works |
|---|---|
| **Safety veto** | Safety Agent blocks Planner's `forward` call → returns `{"status": "vetoed"}` |
| **Reflex override** | Reflex Agent (30 Hz) overrides Planner at Arbiter → motors stop |
| **Parser shortcut** | Parser Agent skips Planner entirely for simple commands → direct execution |
| **Watchdog halt** | If both Reflex and Planner go stale for 0.5s → motors halt |
| **Spatial feedback** | Mapper shows Planner explored/occupied areas via `check_map` and `get_obstacles` |
| **Inner Monologue** | Real execution results fed back to Planner → brain reacts within same episode |
| **RAG retrieval** | Brain calls `search_knowledge` → retrieves protocols + past encounters |
| **Memory logging** | Brain calls `log_finding` → persists discovery in Backboard memory |
| **Pattern analysis** | Brain calls `analyze_patterns` → Backboard analyzes all stored memory |

---

## Key Scenarios (Sequence Flows)

### Scenario 1: Voice command "forward 2 meters"

```
1. Pi mic → FFmpeg ALSA → TCP → laptop
2. STT Agent: audio → "forward 2 meters" (final transcript)
3. Transcript downstream: laptop → Pi (piggybacked on depth JSON)
4. Pi client: on_transcript → TranscriptBuffer.push()
5. Brain loop: consume_final() → state.last_user_command
6. Parser Agent: "forward 2 meters" → {"verb": "forward", "args": {"distance_m": 2.0}}
7. Safety Agent: check forward against detections → OK
8. Controller: forward(2.0) → cmd_vel → arbiter → motors
9. Reflex Agent (30 Hz): monitors clearance during execution
10. Result: {"status": "completed"} → Inner Monologue → Planner knows it moved
11. Mapper Agent: update trail + sensor readings → WebSocket → frontend
```

### Scenario 2: Obstacle detected during forward motion

```
1. Reflex Agent (30 Hz): reads detections → obstacle within 0.3m
2. Reflex Agent: sets reflex_cmd = (0, 0) → arbiter overrides brain
3. Arbiter: outputs (0, 0) → motors stop
4. Brain episode: forward() returns {"status": "stopped_by_obstacle"}
5. Planner Agent: receives "stopped_by_obstacle" via Inner Monologue
6. Planner calls check_map(3.0) → Mapper returns nearby obstacles
7. Planner calls turn(50) → Safety: OK (turn not gated) → execute
8. Mapper Agent: ray-casts obstacle onto grid (occupied cells)
```

### Scenario 3: Distress call + RAG retrieval + victim communication

```
1. STT Agent: transcribes "help me" → TranscriptBuffer
2. Brain loop: consume_final() → state.last_user_command = "help me"
3. Parser Agent: "help me" → None (not a simple verb)
4. Planner Agent: receives "help me" as user command
5. Planner calls search_knowledge("victim communication")
   └── Backboard RAG retrieves victim communication protocol
   └── Returns: "Speak calmly, ask name and injuries, don't promise timelines"
6. Planner calls speak("I hear you. I'm a rescue rover. Help is on the way.")
   └── TTS Agent (ElevenLabs): speaks to victim (async)
7. Planner calls forward(1.0) → approach the sound
8. Planner calls log_finding("survivor", "distress call at (2.3, 1.1)")
   └── Backboard memory: add_memory with metadata
9. Mapper Agent: add_sound(pose, "distress", "help me", 85) → sound marker on map
10. Frontend: displays directional danger soundwave + speech marker
```

### Scenario 4: Thermal hazard + pattern analysis

```
1. Brain calls get_temperature() → returns {celsius: 72, status: "overheat"}
2. Brain calls search_knowledge("thermal hazard approach")
   └── Backboard RAG retrieves thermal protocol
   └── Returns: "Stop, announce temperature, find alternate route"
3. Brain calls speak("I detect high heat at 72°C. Rerouting.")
4. Brain calls check_map(3.0) → Mapper returns nearby obstacles
5. Brain calls turn(90) → route around hazard
6. Brain calls log_finding("hazard", "overheat 72C at (1.5, 0.5)")
7. Brain calls analyze_patterns()
   └── Backboard get_memory_insights analyzes all stored memory
   └── Returns: "Public infrastructure had 75% rescue rate vs 33% residential"
8. Mapper Agent: add_heat(pose, 72, "overheat") → red heat dome on map
```

### Scenario 5: Cloud failure (graceful degradation)

```
1. Wi-Fi drops → Backboard, Baseten, ElevenLabs all fail
2. Reflex Agent (30 Hz): continues running (no cloud dependency)
3. Reflex Agent: monitors obstacles, stops at walls, keeps rover safe
4. Pose Agent: continues dead-reckoning (no cloud dependency)
5. Mapper Agent: continues building map from onboard sensors (no cloud)
6. Brain loop: try/except catches cloud failures, keeps prior scene_description
7. Arbiter: watchdog halts if no brain command for 0.5s, reflex still active
8. Rover: safe but silent — drives by reflex only, no deliberation
```
