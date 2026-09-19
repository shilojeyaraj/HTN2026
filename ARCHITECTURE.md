# Agent Architecture & Data Flow

How inputs move through the rover: from a spoken word to motor commands.
Read this alongside the code — every arrow below maps to a real function call.

---

## The two loops

```
FAST REFLEX LOOP (~30 Hz, onboard, no cloud)          SLOW DELIBERATIVE LOOP (~1 Hz, cloud)
┌─────────────────────────────┐                       ┌──────────────────────────────────┐
│  OAK-D detections           │                       │  Camera frame + detections       │
│        │                    │                       │  + temperature + audio + gyro    │
│        v                    │                       │        │                         │
│  obstacle < 0.3m ahead?     │                       │        v                         │
│        │                    │                       │  Gemini vision (via Backboard)  │
│   yes  │  no                │                       │  → scene_description             │
│   v    v                   │                       │        │                         │
│  STOP   pass-through        │  <-- arbiter          │        v                         │
│         │                   │     priority mux      │  Command parser (Baseten)        │
│         v                   │                       │  → fast path or Backboard brain │
│  /cmd_vel to motors         │                       │  → tool calls → verbs           │
└─────────────────────────────┘                       │  → safety gate → arbiter        │
                                                      └──────────────────────────────────┘
```

The reflex loop always wins at the arbiter. If wifi dies, the robot still stops at walls.

---

## Input channels (three ways the rover learns about the world)

```
1. CAMERA (always on, every episode)
   OAK-D → frame + depth + detections → Gemini vision → scene_description
   Also feeds the reflex loop (obstacle detection for emergency stop)

2. ENVIRONMENTAL SENSORS (brain polls on demand via tool calls)
   get_temperature() → {celsius, status}     fire/overheat detection
   get_audio()       → {db, event}           distress calls, hazard noise, voices
   get_gyro()        → {pitch, roll, tipped}  tipping, impact, pickup detection

3. VOICE (two modes)
   a. AMBIENT LISTENING (autonomous, no button)
      The brain calls get_audio() to poll the mic for screams/hazard noise.
      If it detects distress, it responds autonomously: speak() + approach.
      This is the primary rescue interaction — no human operator needed.

   b. PUSH-TO-TALK (operator override, optional)
      GPIO button held → record → Baseten STT → last_user_command
      An operator can give a direct command ("stop", "go left", "report status").
      This interrupts the idle wait between episodes via wake_event.
      Optional for the demo — the rover works without it.
```

## Full pipeline: spoken command to motor action

### Step 1 — Voice capture (event-driven, not polled)

```
GPIO button held
    │
    v
voice/push_to_talk.py: PushToTalkLoop.run_forever()
    │  polls is_held() at 20 Hz
    │
    v
voice/stt.py: record_while_held(is_held)
    │  records mic via sounddevice (16kHz mono int16)
    │  stops when button released
    │  writes WAV to tempfile
    │
    v
voice/stt.py: transcribe(audio_path)
    │  POST https://model-{BASETEN_STT_MODEL_ID}.api.baseten.co/predict
    │  Body: {"whisper_input": {"audio": {"audio_b64": "<base64>"},
    │                             "whisper_params": {"audio_language": "en"}}}
    │  Header: Authorization: Api-Key {BASETEN_API_KEY}
    │  Response: {"segments": [{"text": "forward two meters"}, ...]}
    │  Returns: "forward two meters"
    │
    v
state.last_user_command = "forward two meters"
wake_event.set()  ← interrupts main loop's idle wait
```

### Step 2 — Deliberative episode starts (brain/loop.py: run_episode)

```
main.py main loop:
    state = run_episode(state, arbiter)
    wake_event.wait(timeout=1.0)   ← sleeps here until button press or 1s timeout
    wake_event.clear()
```

### Step 3 — Perception (top of run_episode)

```
brain/loop.py: _perceive(state)
    │
    ├─ perception/camera.py: get_latest_frame()
    │   └─ OAK-D → (jpeg_bytes, [Detection, ...])
    │
    ├─ perception/vision.py: describe_scene(jpeg_bytes, detections)
    │   │
    │   │  writes jpeg to tempfile
    │   │
    │   v
    │   brain/backboard_client.py: brain.describe(content, image_path)
    │   │
    │   v
    │   Backboard SDK: send_message(
    │       content="Describe the scene in 2-3 sentences...\nDetections: [...]",
    │       input_image="/tmp/xxx.jpg",        ← SDK uploads this as attachment
    │       llm_provider="google",
    │       model_name="gemini-2.5-flash",
    │       thread_id=<persistent>,
    │   )
    │   │
    │   v
    │   Returns: "A hallway with a chair 1.2m ahead. Open space on the left."
    │
    v
    state.scene_description = "A hallway with a chair 1.2m ahead..."
    state.detections = [{label, distance_m, bearing_deg, bbox}, ...]
```

### Step 4a — Fast path: command parser (skips Backboard for simple commands)

```
if state.last_user_command:

    brain/command_parser.py: parse("forward two meters")
        │
        │  POST https://model-{BASETEN_PARSER_MODEL_ID}.api.baseten.co/predict
        │  Body: {"prompt": "forward two meters", "max_new_tokens": 128}
        │  Header: Authorization: Api-Key {BASETEN_API_KEY}
        │  Response: {"output": "{\"verb\": \"forward\", \"args\": {\"distance_m\": 2.0}}"}
        │
        v
    parsed = {"verb": "forward", "args": {"distance_m": 2.0}}

    if parsed is not None:
        _execute_verb("forward", {"distance_m": 2.0}, state, arbiter)
        return  ← episode done, no Backboard call
```

### Step 4b — Slow path: Backboard brain (complex commands or no command)

```
user_content = (
    f"Scene: {state.scene_description}\n"
    f"Current goal: {state.current_goal}\n"
    f"User command: {state.last_user_command}\n"
    f"Pose: {state.robot_pose}"
)

brain/backboard_client.py: brain.run_tools(
    content=user_content,
    system_prompt=SYSTEM_PROMPT,     ← "You are a rescue rover..."
    tools=VERBS,                      ← 7 OpenAI-style function defs
    execute_tool=execute_tool,        ← callback that runs _execute_verb
    memory="Auto",                    ← Backboard manages conversation history
)
```

### Step 5 — Backboard send_message (inside _run_tools)

```
BackboardClient.send_message(
    content=user_content,
    system_prompt=SYSTEM_PROMPT,
    llm_provider="google",
    model_name="gemini-2.5-pro",
    tools=VERBS,                       ← see Step 6 for the schema
    thread_id=self.thread_id,          ← None on first call, then persisted
    assistant_id=self.assistant_id,
    memory="Auto",
)
│
v
ChatMessagesResponse:
    .status       = "REQUIRES_ACTION"   ← model wants to call tools
    .tool_calls   = [ToolCall(id, type, function)]
    .thread_id    = UUID                ← save for next episode
    .assistant_id = UUID
    .content      = None                ← no text yet, just tool calls
```

### Step 6 — The verb tool schema (what the model sees)

```json
[
  {"type": "function", "function": {
    "name": "forward",
    "description": "Drive forward distance_m meters, then stop. Returns 'completed' or 'stopped_by_obstacle'.",
    "parameters": {"type": "object", "properties": {"distance_m": {"type": "number"}}, "required": ["distance_m"]}
  }},
  {"type": "function", "function": {"name": "backward", ...}},
  {"type": "function", "function": {"name": "turn", "parameters": {"properties": {"degrees": {"type": "number"}}, "required": ["degrees"]}}},
  {"type": "function", "function": {"name": "stop", ...}},
  {"type": "function", "function": {"name": "speak", "parameters": {"properties": {"text": {"type": "string"}}, "required": ["text"]}}},
  {"type": "function", "function": {"name": "get_obstacles", ...}},
  {"type": "function", "function": {"name": "get_state", ...}},
  {"type": "function", "function": {"name": "get_temperature", "description": "Read ambient temperature. Returns {celsius, status: ok|warm|overheat}"}},
  {"type": "function", "function": {"name": "get_audio", "description": "Read mic for distress/hazard/voice events. Returns {db, event: {kind, label, text, bearing_deg}|null}"}},
  {"type": "function", "function": {"name": "get_gyro", "description": "Read IMU for tilt/impact. Returns {pitch_deg, roll_deg, accel_z_g, tipped, bump}"}}
]
```

### Step 7 — Tool execution + Inner Monologue loop

```
while response.status == "REQUIRES_ACTION" and rounds < 6:

    for call in response.tool_calls:
        │
        │  call.function.name      = "forward"
        │  call.function.arguments = '{"distance_m": 2.0}'  ← JSON string, not dict
        │
        v
        args = json.loads(call.function.arguments)
        result = execute_tool("forward", {"distance_m": 2.0})
            │
            v
            _execute_verb("forward", {"distance_m": 2.0}, state, arbiter)
                │
                ├─ "speak" → voice/tts.py: speak(text)
                │   └─ async thread → ElevenLabs API → mpv playback
                │
                ├─ "get_obstacles" → return {detections: [...]}
                ├─ "get_state" → return {pose, velocity, goal}
                ├─ "get_temperature" → perception/sensors.py: read_temperature()
                │   └─ return {celsius: 24.3, status: "ok"}
                ├─ "get_audio" → perception/sensors.py: read_audio()
                │   └─ return {db: 62.0, event: {kind: "distress", label: "scream", bearing_deg: -25}}
                ├─ "get_gyro" → perception/sensors.py: read_gyro()
                │   └─ return {pitch_deg: 2.1, roll_deg: -0.3, tipped: false, bump: false}
                │
                └─ movement verb (forward/backward/turn/stop):
                    │
                    v
                    brain/safety.py: check("forward", args, detections)
                        │  SayCan gate: only "forward" is gated
                        │  if obstacle within 0.4m at |bearing| < 30° → VETO
                        │
                        ├─ VETO → return {"status": "vetoed", "reason": "obstacle ahead"}
                        │
                        v
                        control/controller.py: execute_verb("forward", args, arbiter, get_detections)
                            │
                            │  Drives at 0.3 m/s for distance/speed seconds
                            │  Polls for obstacles at 20 Hz
                            │  If obstacle within 0.3m → stop, return "stopped_by_obstacle"
                            │  Otherwise → return "completed"
                            │
                            │  Each poll calls arbiter.set_brain_cmd(linear, angular)
                            v
                            return {"status": "completed"}
                                          OR
                            return {"status": "stopped_by_obstacle", "distance_m": 0.8}

        tool_outputs.append({
            "tool_call_id": call.id,
            "output": '{"status": "completed"}'  ← JSON string
        })

    │
    v
    Backboard SDK: submit_tool_outputs_simple(
        thread_id=response.thread_id,
        tool_outputs=tool_outputs,
    )
    │
    v
    Backboard sends tool results back to the LLM
    LLM reacts: "forward stopped by obstacle at 0.8m → I should turn right"
    Returns new response (maybe more tool calls, or final text)
```

### Step 8 — Arbiter (priority mux, always running)

```
control/arbiter.py: Arbiter.tick() at 30 Hz
    │
    │  reflex_cmd fresh (< 0.5s old)?
    │    ├─ yes → publish reflex_cmd (emergency stop wins)
    │    │
    │  brain_cmd fresh (< 0.5s old)?
    │    ├─ yes → publish brain_cmd (normal driving)
    │    │
    │  both stale → publish (0.0, 0.0)  ← watchdog halt
    │
    v
    publish_cmd_vel(linear, angular)
        └─ currently: lambda l, a: None  (no-op)
        └─ on Pi: ROS2 Twist publisher → /cmd_vel → motors
```

### Step 9 — Reflex loop (always running, no cloud)

```
control/reflex.py: ReflexLoop.tick() at 30 Hz
    │
    │  detections = get_latest_detections()
    │  blocked = any obstacle with distance < 0.3m and |bearing| < 30°
    │
    ├─ blocked → arbiter.set_reflex_cmd((0.0, 0.0))   ← override brain
    └─ clear  → arbiter.set_reflex_cmd(None)           ← let brain through
```

---

## What goes where: sponsor slices

```
Sponsor      Module                        Cloud call
─────────────────────────────────────────────────────────────
Backboard    brain/backboard_client.py     send_message() + submit_tool_outputs_simple()
                                           llm_provider="google", model_name="gemini-2.5-pro"
                                           (also: vision via input_image= with gemini-2.5-flash)

Baseten     voice/stt.py                  POST to Baseten Whisper predict endpoint
            brain/command_parser.py        POST to Baseten fine-tuned model predict endpoint
            training/                      baseten train push --config config.py

ElevenLabs  voice/tts.py                  client.text_to_speech.convert()
                                           model_id="eleven_flash_v2_5"

Gemini      (routed through Backboard      send_message(llm_provider="google", ...)
             as BYOK, not direct SDK)       vision: input_image= path to jpeg
```

---

## State that flows between episodes

```python
# brain/state.py: RobotState
RobotState(
    timestamp=0.0,
    robot_pose=(0.0, 0.0, 0.0),      # x, y, heading (if odometry available)
    velocity=(0.0, 0.0),              # linear, angular
    detections=[],                    # from OAK-D: [{label, distance_m, bearing_deg, bbox}]
    scene_description=None,           # from Gemini vision: "A hallway with..."
    current_goal=None,                # (x, y) target or None
    last_user_command=None,           # from Baseten STT: "forward two meters"
    safety_status="OK",              # "OK" or "VETO"
)
```

The `thread_id` on `BackboardBrain` persists across episodes — that's what makes
`memory="Auto"` useful. The LLM remembers the conversation history from prior
ticks without us managing it.

---

## Key invariants

1. **Cloud calls never touch the reflex loop.** Reflex is pure onboard classical code at 30 Hz.
2. **The reflex loop always wins at the arbiter.** Safety before smartness.
3. **Voice I/O never blocks the control loop.** TTS is async (threading.Thread), STT is event-driven (wake_event).
4. **Watchdog halts the robot** if no fresh command arrives within 0.5s.
5. **Each verb self-completes and returns a real status.** This is what powers Inner Monologue — the LLM learns forward() stopped at 0.8m and can decide to turn().
6. **The command parser is a fast path, not a replacement.** Simple commands skip Backboard entirely; complex ones fall through to the full brain.
