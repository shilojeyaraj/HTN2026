# CLAUDE.md

Project context for an autonomous voice-interactive rover built at Hack the North 2026.
Single source of truth for the build. Companion docs: **BACKBOARD.md** (the brain's API) and **PRIZE_TRACKS.md** (sponsor tracks and scopes). Read all three before writing code.

---

## 1. Event context

- **Event:** Hack the North 2026, University of Waterloo, Sept 18 to 20 (36 hours).
- **Judging:** WOW factor, technical ability, originality, design. The pitch is a **live demo**, not slides. The robot must physically move.
- **Committed tracks:** Backboard, Baseten, Gemini, ElevenLabs, Rox. openJiuwen stacks cleanly. Full scopes and the role-per-sponsor split are in PRIZE_TRACKS.md.
- **Prize claims are due on Devpost by 2:00 PM EDT Saturday.** Assign an owner.

---

## 2. What we are building

A small differential-drive rover that perceives with a camera, reasons with an LLM agent brain, and can be spoken to and talk back. It drives itself, avoids obstacles, takes spoken commands, and narrates what it is doing.

Core technical story: **a hierarchical two-loop architecture** where fast reflexes keep the robot safe while a slower LLM brain does the thinking. This is both the honest engineering and the demo narrative.

---

## 3. Architecture: the two-loop design (READ THIS FIRST)

Everything follows from one constraint: **cloud calls take 0.5 to 3 seconds, far too slow for a control loop.** So two loops run at different speeds.

### Fast reflex loop (~30 Hz, onboard, classical, NO LLM, NO cloud)
- Runs entirely on the host. No network dependency.
- Reads depth / detections, does emergency stop and obstacle avoidance.
- Has **final authority over `cmd_vel`** and can override the brain.
- MUST keep the robot safe even if every cloud call times out and wifi dies.

### Slow deliberative loop (~1 Hz, cloud, the brain)
- Reasons over the scene, plans the next move, handles voice.
- Emits movement intent and goals, never raw motor commands.
- Is allowed to be slow and to fail. When it fails, the reflex loop holds.

### Pipeline
```
Camera --> Perception --> Brain (Backboard) --> Arbiter --> Controller --> Motors
  |            |               |                   ^
  |            |               v                   |
  |            |          ElevenLabs (voice out)   |
  +-- depth / detections ----------------- reflex loop (fast, safety, wins at the arbiter)
```

---

## 4. The brain: Backboard core + direct integrations

Backboard is the deliberative brain. See BACKBOARD.md for API detail. The other three sponsors each own a **distinct, directly-called slice** so they count for their own tracks instead of being proxied under Backboard (see PRIZE_TRACKS.md for why).

- **Backboard = core.** Agent loop, tool calling, thread state, planner model routing, and (optional, high value) memory. It is a cloud API, so it lives in the slow loop only.
- **Gemini = vision / scene understanding**, called directly via the Gemini API.
- **ElevenLabs = voice out**, called directly.
- **Baseten = voice in (STT)**, called directly, plus the optional command-parser fine-tune (see section 12 and TRAINING notes).

**openJiuwen (multi-agent) tie-in:** route distinct roles (scene, planner, safety) to distinct models inside Backboard. That heterogeneous split is the genuine multi-agent system the track rewards. Do not collapse it into one prompt.

### Environment variables (never hardcode keys)
```
BACKBOARD_API_KEY
GEMINI_API_KEY
ELEVENLABS_API_KEY
BASETEN_API_KEY
```

---

## 5. The agent loop (deliberative tick, ~1 Hz)

### Shared state
```
timestamp
robot_pose        # if odometry available
velocity          # current linear + angular
detections[]      # from perception: label, distance, bearing
scene_description # structured output from the vision step
current_goal
last_user_command
planned_action
safety_status     # OK or VETO
```

### Tick
1. Snapshot inputs: downscaled RGB frame + detections + robot state.
2. **Vision:** frame -> Gemini (direct) -> structured scene (obstacles, free space, notable objects).
3. **Plan:** send scene + goal + any user command into the Backboard thread (planner model + tools + memory) -> tool calls.
4. **Safety monitor:** validate the planned action against latest detections (fast model via Backboard, or classical). On conflict, VETO -> safe fallback (usually stop).
5. **Execute** the tool calls: movement intent goes to the arbiter (section 6), never straight to motors.
6. If `speak()` was called, fire ElevenLabs TTS **asynchronously** (never block the tick).

### Voice-in (event-driven)
Push-to-talk (hold a button) -> Baseten STT -> injected as `last_user_command` for the next tick. Do NOT use audio-to-audio conversational mode; the robot must emit tool calls, which live in the text layer.

---

## 6. Movement tools (CRUD-for-motion) and the arbiter

The brain drives through a small fixed verb set, like CRUD but for motion. A verb expresses **intent**; it never touches motors directly.

### Verbs (the tool schema)
```
forward(distance_m: float)   # drive forward, then stop
backward(distance_m: float)  # drive back, then stop
turn(degrees: float)         # + left, - right, then stop
stop()                       # halt
speak(text: str)             # ElevenLabs TTS
# read side: get_obstacles(), get_state()
```
Make verbs **bounded and self-completing**: `forward(0.5)` drives ~0.5 m (open-loop time = distance / speed is fine), stops, and returns a status (`completed` or `stopped_by_obstacle` with distance). This keeps the loop clean and gives the brain feedback to reason with. Keep `set_goal(x, y)` as an upgrade only if odometry ends up solid.

### Verb to velocity
A handler turns each verb into a `geometry_msgs/Twist`: `linear.x` = forward/back speed, `angular.z` = turn rate. The base controller splits Twist into wheels via differential-drive kinematics (left = `linear.x - angular.z * wheelbase/2`, right = `linear.x + angular.z * wheelbase/2`).

### Arbitration and watchdog (build these, do not skip)
- The brain publishes to a **low-priority** intent topic; the reflex loop publishes to a **high-priority** one; a mux (`twist_mux`, or a ~30-line node) outputs final `/cmd_vel` with the reflex winning.
- The base controller **stops if no fresh command arrives within ~0.5 s** (watchdog). If the software hangs, the robot halts instead of driving into a wall.

---

## 7. Driving / navigation layer

### Reflex loop = the safety floor (build first)
A minimal onboard node: read depth / detections, emergency-stop and simple avoidance, publish high-priority `cmd_vel`. No cloud, no LLM. A robot that reliably stops at a wall with zero cloud involved is the floor everything else sits on. Build and test this before any LLM touches the wheels.

### Optional upgrade: learned local nav (NoMaD / ViNT)
`robodhruv/visualnav-transformer` (MIT) ships pretrained camera-only navigation policies. NoMaD's exploration mode gives collision-avoiding wandering from a single camera with no map; path-following mode repeats a teleoperated route.
- **Take the inference core, not their ROS stack.** Their deploy code is ROS 1 (Noetic); we are ROS 2. Lift the image-to-waypoint core (fastest via the `general-navigation` pip package), feed it our camera frames, take its waypoint into our own controller. Do NOT try to bridge ROS 1/2 under time pressure.
- **Needs a GPU** (Jetson Orin Nano class); NoMaD is a diffusion policy and will not run usably on a bare Pi 5. Only in scope if we have that compute.
- **Goal interface is an image**, not coordinates. Bridging "go to the kitchen" to a goal image is a real step.
- **Keep the emergency stop underneath it.** It is a learned policy that can still fail.

### Techniques to follow (design rules, from the LLM-robotics literature)
- **Code as Policies:** give the brain a clean, well-named primitive API and let it compose calls. This is why the verb schema in section 6 stays small and stable.
- **SayCan (affordance grounding):** the brain proposes, feasibility gates it. That is exactly our arbiter / safety monitor.
- **Inner Monologue:** feed execution results back to the brain as text (`completed`, `stopped_by_obstacle`, what was seen). This closes the loop and is most of what "drives well" actually means. Not optional.

---

## 8. Hardware

- **Host / compute:** Raspberry Pi 5 (4 GB) for ROS 2, capture/playback, the agent loop, and cloud calls. NoMaD (section 7) needs a Jetson Orin Nano or a tethered laptop GPU instead.
- **Camera (primary):** Luxonis OAK-D S2 (on-camera AI, pairs with the Pi, gives depth + on-device detection). Alternative: ZED 2 only if an NVIDIA host is available (better odometry, higher setup risk).
- **Audio:** USB webcam mic (capture), powered USB/BT speaker (playback), push button (push-to-talk). Avoid analog "sound sensor" modules; they only detect loudness.
- **Chassis:** differential-drive base + motor driver. **TODO: confirm** (DJI Robomaster, ESP32 car kits, custom base, or Bracket Bot base if we chase that track).

---

## 9. Software stack

- **Python** primary.
- **ROS 2** (Jazzy on 24.04, or Humble on 22.04). Motor commands are `Twist` on `/cmd_vel`.
- **Camera SDK:** DepthAI (OAK-D).
- **Brain:** Backboard SDK (`backboard-sdk`). Direct clients for Gemini, ElevenLabs, Baseten (all OpenAI-compatible where it matters, so each is a `(base_url, model)` pair).
- **Reflex controller:** minimal custom ROS 2 node. Nav2 optional if odometry is solid.

---

## 10. Critical rules (the agent MUST follow)

- **NEVER put a cloud call (Backboard, Gemini, ElevenLabs, Baseten) in the fast reflex loop.** Reflex is onboard, classical, network-independent.
- **The reflex loop always wins** at the arbiter. Safety before smartness.
- **NEVER let voice / STT / TTS block the control loop.** All audio I/O is async.
- **Watchdog stops the robot** if no fresh command in ~0.5 s.
- **Throttle the deliberative loop to ~1 Hz**, exponential backoff on 429, keep the fixed prompt prefix at the top for caching.
- **Degrade gracefully:** on any cloud failure the robot slows or stops safely and keeps running. Conference wifi is unreliable; assume it.
- **Keys from environment variables**, never committed. Baseten credits are workspace-level (one owner redeems once).
- Keep each sponsor's slice **directly called** (see section 4) so the tracks count.

---

## 11. Proposed repo structure

```
/
  CLAUDE.md  BACKBOARD.md  PRIZE_TRACKS.md
  .env.example              # names only, no real keys
  perception/
    camera.py               # capture, depth, detections
    vision.py               # frame -> Gemini -> structured scene
  brain/
    loop.py                 # deliberative tick
    backboard_client.py     # assistant, thread, tools, memory
    tools.py                # movement verb definitions
    safety.py               # veto logic
  control/
    reflex.py               # fast onboard safety loop (ROS 2)
    arbiter.py              # twist_mux / priority mux
    controller.py           # verb -> Twist -> wheels, watchdog
  nav/
    nomad_core.py           # optional: image -> waypoint wrapper
  voice/
    stt.py                  # push-to-talk + Baseten STT
    tts.py                  # ElevenLabs playback (async)
  ros2_ws/
```

---

## 12. Commands

TODO: fill in once scaffolded.
```
# setup
# run reflex loop only
# run brain loop
# run full stack
```

---

## 13. Open decisions / TODO

- [ ] Confirm chassis and motor driver, plus power/battery (critical path).
- [ ] Confirm camera + compute: OAK-D + Pi (default) vs a GPU host if using NoMaD.
- [ ] Decide whether to use Backboard memory (optional, strong demo beat).
- [ ] Decide whether to attempt the Baseten command-parser fine-tune (side quest, only after the robot works).
- [ ] Smoke-test all four cloud keys before building.
- [ ] Scaffold repo, fill in section 12 commands.