# Agent Flow Diagram

How the rescue rover's agent processes inputs and decides actions,
broken up by domain. Designed for Napkin AI diagram generation — each
section is a self-contained flowchart.

---

## Shared Overview

The rover runs two loops simultaneously:

1. **Fast Reflex Loop (30 Hz, 33ms, no cloud)** — safety, always running
2. **Slow Deliberative Loop (~1 Hz, 1-3s, cloud LLM)** — thinking, voice, planning

The reflex loop always wins at the arbiter. If wifi dies, the robot still
stops at walls. The brain is allowed to be slow; the reflex loop never is.

---

## 1. Visual Detection Flow

How the rover sees and understands its environment.

```
OAK-D S2 Camera (always on)
    ↓
    get_latest_frame()
    Returns: JPEG frame + depth detections
    Latency: ~30-50ms (on-device, no cloud)
    ↓
    Splits into two paths:
    ├─ REFLEX PATH (fast, 30 Hz, no cloud)
    │   ↓
    │   Any obstacle within 0.3m at |bearing| < 30°?
    │   ├─ YES → emergency STOP (override brain)
    │   └─ NO  → pass-through (let brain drive)
    │
    └─ BRAIN PATH (slow, ~1 Hz, cloud)
        ↓
        Gemini 2.5 Flash (via Backboard send_message, input_image=)
        Input: JPEG frame + detection list
        Cloud latency: 500ms-2s
        ↓
        Returns scene description:
        "A hallway with a chair 1.2m ahead. Open space on the left."
        ↓
        Stored in state.scene_description
        Fed to the brain for planning (see section 5)
```

**Input:** camera frame + depth
**Processing:** Gemini vision via Backboard (cloud) + local obstacle check (reflex)
**Output:** scene_description text (for brain) + emergency stop signal (for reflex)
**Total latency:** 50ms (reflex) / 500ms-2s (brain vision)

---

## 2. Speech Flow (Voice In + Voice Out)

How the rover listens and speaks.

### Voice In — Mode A: Ambient Listening (autonomous, primary rescue mode)

```
Brain calls get_audio() as a tool during deliberative tick
    ↓
    perception/sensors.py: read_audio()
    Returns: {db: float, event: {kind, label, text, bearing_deg}|null}
    ↓
    Event kinds:
    ├─ "distress" → screams, calls for help
    │   ↓
    │   Brain responds autonomously: speak() + approach survivor
    │   No button pressed, no operator needed
    │
    ├─ "sound" → hazard noise (rubble, creaking)
    │   ↓
    │   Brain logs hazard, may redirect exploration
    │
    └─ "voice" → operator command detected
        ↓
        Brain treats as a spoken command, acknowledges and acts
```

**Input:** microphone (ambient, always listening)
**Processing:** audio classification (local or cloud model)
**Output:** event with kind/label/bearing → brain decides response
**Latency:** <1ms (stub) / ~100-300ms (real mic + classification)
**Key point:** this is the PRIMARY way the rover finds survivors — no button needed

### Voice In — Mode B: Push-to-Talk (operator override, optional)

```
GPIO button held (pin 17)
    ↓
    voice/push_to_talk.py: record audio while button is held
    Records at 16kHz mono int16 via sounddevice
    ↓
    voice/stt.py: transcribe(audio_path)
    POST to Baseten Whisper model endpoint
    Body: {"whisper_input": {"audio": {"audio_b64": "<base64>"}}}
    Cloud latency: 300-800ms
    ↓
    Returns transcribed text: "forward two meters"
    ↓
    Stored in state.last_user_command
    Sets wake_event → interrupts idle wait between episodes
    ↓
    Routed to command parser (see section 5, fast path)
```

**Input:** button press + microphone
**Processing:** Baseten Whisper STT (cloud)
**Output:** transcribed text → command parser or brain
**Latency:** 300-800ms (cloud) + recording time
**Key point:** optional — the rover works without this

### Voice Out — Text to Speech

```
Brain calls speak("I found someone ahead, approaching now")
    ↓
    voice/tts.py: speak(text)
    ↓
    Fires on a separate thread (async, never blocks control loop)
    ↓
    ElevenLabs API: client.text_to_speech.convert()
    Model: eleven_flash_v2_5
    Cloud latency: 200-500ms
    ↓
    Returns audio bytes
    ↓
    Plays via mpv on USB/BT speaker
    ↓
    Returns {"status": "completed"} to the brain
```

**Input:** text string from brain's speak() verb
**Processing:** ElevenLabs TTS (cloud, async)
**Output:** spoken audio on speaker
**Latency:** 200-500ms (non-blocking, overlaps with driving)
**Key point:** never blocks the control loop — always async

---

## 3. Movement Flow

How the rover decides to move and executes it.

```
Brain (or command parser) emits a movement verb
    ↓
    Which verb?
    ├─ forward(distance_m)  → drive forward, then stop
    ├─ backward(distance_m) → drive back, then stop
    ├─ turn(degrees)        → rotate in place, then stop
    └─ stop()               → halt immediately
    ↓
    Safety Gate (SayCan): brain/safety.py: check(name, args, detections)
    Only "forward" is gated
    ↓
    Obstacle within 0.4m at |bearing| < 30°?
    ├─ YES → VETO → return {"status": "vetoed", "reason": "obstacle ahead"}
    │        Brain learns it was vetoed, tries a different approach
    │
    └─ NO  → PASS → proceed to controller
        ↓
        control/controller.py: execute_verb(name, args, arbiter)
        ↓
        Drives at 0.3 m/s for (distance / speed) seconds
        Polls obstacles at 20 Hz during drive
        ↓
        Obstacle within 0.3m during drive?
        ├─ YES → stop early, return {"status": "stopped_by_obstacle", "distance_m": 0.8}
        └─ NO  → complete drive, return {"status": "completed"}
        ↓
        Each poll calls arbiter.set_brain_cmd(linear, angular)
        ↓
        Arbiter (see section 6) decides what reaches motors
        ↓
        publish_cmd_vel(linear, angular)
        → differential drive kinematics → left/right wheels
```

**Input:** movement verb + arguments (e.g., forward, 2.0)
**Processing:** safety gate (local, <1ms) → controller drive (local, drive time)
**Output:** cmd_vel to motors
**Latency:** <1ms decision + drive time (e.g., 2m at 0.3m/s = ~6.7s)
**Feedback:** verb returns completed/stopped_by_obstacle → brain learns and adjusts

---

## 4. Environmental Sensor Flow

How the rover detects fire, sound, and physical disturbance.

### Temperature Detection

```
Brain calls get_temperature()
    ↓
    perception/sensors.py: read_temperature()
    Reads DHT22 or DS18B20 sensor (GPIO)
    ↓
    Returns: {celsius: 24.3, status: "ok"}
    ↓
    Status thresholds:
    ├─ < 42°C  → "ok" (normal)
    ├─ 42-55°C → "warm" (possible fire nearby)
    └─ ≥ 55°C  → "overheat" (hazardous, brain should retreat)
    ↓
    Brain uses this to detect fire or hazardous heat
```

**Input:** temperature sensor (GPIO)
**Latency:** <1ms (stub) / ~50ms (real hardware)
**Output:** celsius + status → brain decides whether to retreat or investigate

### Audio Detection (ambient listening, distinct from push-to-talk STT)

```
Brain calls get_audio()
    ↓
    perception/sensors.py: read_audio()
    Reads USB mic, classifies sound
    ↓
    Returns: {db: 62.0, event: null}
    OR
    Returns: {db: 78.5, event: {kind: "distress", label: "scream", text: "help", bearing_deg: -25}}
    ↓
    Event kinds:
    ├─ "distress" → screams, calls for help → brain approaches + speaks
    ├─ "sound"   → rubble, creaking → brain logs hazard
    └─ "voice"   → operator voice → brain treats as command
```

**Input:** USB microphone (ambient, always listening)
**Latency:** <1ms (stub) / ~100-300ms (real mic + classification)
**Output:** dB level + event (if any) → brain decides autonomous response
**Key point:** this is how the rover finds survivors without a button press

### Gyro/IMU Detection

```
Brain calls get_gyro()
    ↓
    perception/sensors.py: read_gyro()
    Reads MPU6050 (I2C) or OAK-D onboard IMU
    ↓
    Returns: {pitch_deg: 2.1, roll_deg: -0.3, accel_z_g: 1.0, tipped: false, bump: false}
    ↓
    Detection logic:
    ├─ |pitch| or |roll| > 45° → tipped = true (robot flipped over)
    ├─ accel_z spike          → bump = true (hit something)
    └─ accel_z ~0             → picked up (someone grabbed the robot)
    ↓
    Brain reacts:
    ├─ tipped → speak("I've fallen over, attempting recovery")
    ├─ bump   → back up and reassess path
    └─ picked up → stop motors, speak("I've been picked up")
```

**Input:** IMU/gyroscope (I2C or OAK-D onboard)
**Latency:** <1ms (stub) / ~10ms (real MPU6050)
**Output:** tilt/impact/orientation → brain detects tipping, collision, pickup

---

## 5. Brain Decision Flow

How the agent reasons over all inputs and decides what to do.

### Fast Path: Command Parser (skips brain for simple commands)

```
Voice command arrives (from push-to-talk STT or ambient voice event)
    ↓
    brain/command_parser.py: parse("forward two meters")
    POST to Baseten fine-tuned Qwen3-1.7B model
    Cloud latency: 100-300ms
    ↓
    Returns: {"verb": "forward", "args": {"distance_m": 2.0}}
    ↓
    Parsed successfully?
    ├─ YES → execute verb directly → episode done (no Backboard call needed)
    │        Simple commands don't need an LLM to reason — just parse and act
    │
    └─ NO  → fall through to slow path (Backboard brain)
```

**Input:** transcribed voice command text
**Processing:** Baseten fine-tuned Qwen3-1.7B (cloud, fast inference)
**Output:** parsed verb + args → direct execution
**Latency:** 100-300ms
**Key point:** saves 1-3s by skipping Backboard for simple commands

### Slow Path: Backboard Brain (complex reasoning)

```
Assemble context from all inputs:
    - Scene description (from Gemini vision)
    - Current goal
    - User command (if any)
    - Robot pose
    ↓
Backboard send_message(
    content = assembled context,
    system_prompt = "You are a rescue rover...",
    tools = [10 verb definitions],
    llm_provider = "google",
    model_name = "gemini-2.5-pro",
    thread_id = <persistent across episodes>,
    memory = "Auto",
)
    Cloud latency: 1-3s per round
    ↓
    Gemini 2.5 Pro reasons over the full context
    ↓
    Returns tool_calls (e.g., [forward(2.0), speak("moving forward now")])
    Status: "REQUIRES_ACTION"
    ↓
    Execute each tool call (see sections 2, 3, 4)
    ↓
    Collect results
    ↓
    Inner Monologue: feed results back to brain
    submit_tool_outputs_simple(thread_id, tool_outputs)
    ↓
    Brain reacts to results:
    "forward stopped by obstacle at 0.8m → I should turn right"
    ↓
    Returns new tool calls (e.g., turn(-90), forward(0.5))
    ↓
    Loop repeats until:
    ├─ status = "COMPLETED" (brain is done, no more tool calls)
    └─ rounds >= 6 (MAX_TOOL_ROUNDS cap, prevents infinite loops)
```

**Input:** scene + goal + command + pose (assembled from all sensors)
**Processing:** Gemini 2.5 Pro via Backboard (cloud), up to 6 rounds
**Output:** tool calls (verbs) → executed → results fed back
**Latency:** 1-3s per round, worst case 6 rounds = ~12-18s
**Memory:** thread persists across episodes — LLM remembers prior ticks

---

## 6. Arbiter + Reflex Flow (safety, always running)

How the rover decides what actually reaches the motors.

### Reflex Loop (30 Hz, no cloud, safety floor)

```
Every 33ms:
    ↓
    Read latest OAK-D detections
    ↓
    Any obstacle within 0.3m at |bearing| < 30°?
    ├─ YES → arbiter.set_reflex_cmd((0.0, 0.0))  → STOP, override brain
    └─ NO  → arbiter.set_reflex_cmd(None)         → let brain through
    ↓
    No cloud, no LLM, pure classical safety
    If wifi dies and brain crashes, this loop still stops the robot at walls
```

### Arbiter (priority mux, 30 Hz)

```
Every 33ms, decide what reaches the motors:

    Reflex command fresh (< 0.5s old)?
    ├─ YES → publish reflex_cmd (EMERGENCY STOP WINS, always)
    │
    Brain command fresh (< 0.5s old)?
    ├─ YES → publish brain_cmd (normal driving)
    │
    Both stale (no command in 0.5s)?
    └─ YES → publish (0.0, 0.0) (WATCHDOG HALT, robot stops safely)
    ↓
    publish_cmd_vel(linear, angular) → motors
```

**Priority order:** reflex (emergency stop) > brain (driving) > watchdog (halt)
**Watchdog:** if software hangs, robot halts instead of driving into a wall
**Latency:** <1ms per tick

---

## The 10 Verbs (the agent's entire action space)

| Verb | Domain | Cloud? | Returns |
|------|--------|--------|---------|
| `forward(distance_m)` | movement | no | completed / stopped_by_obstacle |
| `backward(distance_m)` | movement | no | completed / stopped_by_obstacle |
| `turn(degrees)` | movement | no | completed |
| `stop()` | movement | no | completed |
| `speak(text)` | speech out | yes (ElevenLabs, async) | completed |
| `get_obstacles()` | visual | no | {detections: [...]} |
| `get_state()` | movement | no | {pose, velocity, goal} |
| `get_temperature()` | sensors | no | {celsius, status} |
| `get_audio()` | sensors | no | {db, event} |
| `get_gyro()` | sensors | no | {pitch, roll, tipped, bump} |

The brain can only act through these 10 verbs. It cannot invent motor commands.
This is the "Code as Policies" pattern — a small, stable, well-named primitive API.

---

## Timing Summary

| Scenario | Path | Decision latency |
|----------|------|-----------------|
| Reflex emergency stop | OAK-D → obstacle check → arbiter | 33ms |
| Simple voice command | STT → parser → safety gate → drive | ~700ms |
| Complex command (1 round) | perception → brain → safety gate → drive | ~3.5s |
| Complex command (3 rounds) | perception → 3x brain+tool → drive | ~7.5s |
| Worst case (6 rounds) | perception → 6x brain+tool → drive | ~13.5s |
| TTS (async, overlaps) | speak() → ElevenLabs → speaker | 200-500ms |
