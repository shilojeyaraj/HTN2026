# HTN 2026 rover

The rover uses a DJI RoboMaster EP Core controlled from a Linux laptop over the robot's AP Wi-Fi. All robot I/O is isolated in `control/robomaster.py`; planners and tool handlers never import the DJI SDK.

## Setup

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Connect the laptop to the RoboMaster's Wi-Fi network before running anything that initializes the robot. The controller always connects with `ep.initialize(conn_type="ap")`.

## Physical smoke test

To diagnose chassis execution using the same controller and speeds as the application:

```sh
python3 robomaster_motion_smoke_test.py
```

This standalone script connects to the real robot, moves forward 0.25 m, waits one second, turns 45°, stops, and closes the SDK connection even on failure. It does not invoke perception, planning, or simulation. Run it explicitly with clear space around the loaner robot.

Controller logs include the real SDK action type/repr, state, `wait_for_completed()` result, success/failure flags, failure reason, and elapsed wall time. The SDK's wait returning `True` means the action ended, which includes rejected/failed actions. The controller requires `has_succeeded=True` before reporting completion; otherwise it stops and raises an error. Telemetry is sampled asynchronously, so a cached position in the completion log is not independent proof of displacement.

With clear space around the robot, run:

```sh
python3 robomaster_smoke_test.py
```

By default, the script recentres the arm, moves it 40 mm forward and 30 mm up, opens and closes the gripper at low power, captures a frame from that view, then recentres the arm. It always pauses the gripper and closes the SDK connection.

Chassis motion is opt-in: add `--exercise-chassis` to move forward 0.2 m and turn 30°, or `--exercise-chassis --spin-degrees 360` for one full chassis spin. Every movement value is configurable.

## Agent runtime

```sh
python3 main.py --goal "Explore this room and report people or hazards."
```

The goal is routed locally **before camera capture**:

- **DIRECT:** exact motion commands are parsed once, split into bounded local tool calls, executed once, and the application exits. There are no camera, Gemini, Backboard, or Baseten calls for these commands. Every chunk still passes through the existing argument validator and RoboMaster controller. A failed chunk stops the maneuver; Ctrl+C requests a stop and closes the connection.
- **CLOSED_LOOP:** goals such as “find the red chair”, “approach the person”, or ambiguous/conditional requests retain perception → planning → one physical action → fresh perception. The local parser must match the whole command; “turn 90 if the path is clear” therefore stays closed-loop. Backboard memory and model fallbacks are unchanged.

```sh
python3 main.py --goal "turn 360"
python3 main.py --goal "move forward 1.5 m"
python3 main.py --goal "move backward slightly"
python3 main.py --goal "stop"
```

`turn 360` becomes four `turn(90)` calls; `move forward 1.5 m` becomes two `forward(0.75)` calls. Signed turns use positive = left and negative = right. Numeric translations require metres (`m`, `meters`, or `metres`). “Slightly”, “a little”, and “a small amount” use `SLIGHT_TRANSLATION_M=0.2` and `SLIGHT_TURN_DEG=15` in `brain/direct_commands.py`. A trailing “then stop” appends a local `stop()` call: “move forward a small amount, then stop” stays DIRECT. Other compound or conditional commands still use CLOSED_LOOP. Gripper open/close, arm recenter, and explicit arm moves such as “move arm up 30 mm” also route directly. A spoken direct command overrides the current cycle; “stop” ends the active mission.

Direct mode does not visually check for obstacles between chunks. Chunk sizes come from the tool schemas (0.05–0.75 m, ±90°). Short remainders are redistributed to preserve the requested total; for example, 0.76 m becomes 0.71 + 0.05 m. Zero totals do nothing, totals below the translation minimum are rejected without moving, and `MAX_DIRECT_CHUNKS=100` rejects excessively large requests before execution. Logs report the mode, parsed command, requested total, chunk plan, individual commands, and total duration.

For four direct turn chunks, the fast path removes all four vision and four planner stages, plus inter-cycle waits; only SDK command/completion time and physical movement remain. At 90°/s, 360° has a nominal rotation time of 4 seconds, plus acceleration and SDK overhead. This is an estimate, not a measured hardware benchmark.

The goal accompanies each planner decision alongside the latest scene description. The planner can call bounded `forward`, `backward`, `strafe_left`, `strafe_right`, `turn`, `stop`, `move_arm`, `recenter_arm`, `open_gripper`, and `close_gripper` tools. Motion uses `ep.chassis.move(...).wait_for_completed()`; `stop` uses `ep.chassis.drive_speed(x=0, y=0, z=0)`.

Planner arguments are validated before execution: distances are clamped to 0.05–0.75 m, turns to ±90°, arm deltas to ±80 mm per axis, and speech to 240 characters. Missing/invalid arguments are logged and rejected without moving. Each perception cycle permits at most one chassis, arm, or gripper action. The remaining calls in that batch are marked skipped; tool results are submitted with fresh scene/state on the next cycle before replanning. Failed camera/vision reads block further physical actions until perception succeeds. Terminal logs include requested and clamped arguments, chassis action and xy/z speeds, duration, and rejection details.

The planner favors a meaningful translation (0.3–0.75 m) or turn (30–90°) for a far, obvious target with a visibly open path. Near targets, people, obstacles, or uncertain views call for finer translations (0.05–0.25 m) or turns (5–30°). Default chassis speeds are 0.7 m/s and 90°/s, configured by `DEFAULT_XY_SPEED_MPS` and `DEFAULT_Z_SPEED_DPS` in `control/robomaster.py`. Manual calls can still override speed; the physical smoke test retains its explicit slower 0.5 m/s translation default.

`get_state` exposes only telemetry received from the RoboMaster chassis. `get_obstacles` exposes raw onboard ToF readings in millimetres, with no inferred bearing. Camera frames come from the RoboMaster stream at 360p and are retried when a transient read returns no frame.

### Inference quotas

Both inference routes prefer `gemini-3.6-flash`. A daily quota error switches vision to direct Gemini `gemini-3.5-flash-lite` and planning to `openai/gpt-4.1-mini` through Backboard for the rest of the process. The Backboard fallback uses the existing `BACKBOARD_API_KEY`; no separate OpenAI key is needed. Model/provider overrides are in `.env.example`. Set an empty fallback model to disable that fallback.

Temporary planner limits honor provider retry delays (including HTTP `Retry-After`) and retry up to three times before trying the fallback. These retries keep the current scene, goal, thread, and tool results, without executing actions or starting another episode. Accepted tool results are never submitted again after an embedded provider error. If planner recovery is exhausted, or both vision models exhaust their daily quotas, the mission stops with an actionable error and closes the robot connection.

Vision requests start at least `VISION_MIN_INTERVAL_S=6` seconds apart, with additional cooldown after rate limits. Failed vision skips planning and movement; the next attempt captures a new frame. Backboard still handles planning and memory, and receives only text. Daily quotas cannot be fixed by a short retry: enable billing/increase quota for sustained operation if the configured routes run out. See [Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits).
