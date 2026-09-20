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
- **CLOSED_LOOP:** the current JPEG, goal, chassis state, local mission context, and tool schemas go to one multimodal Gemini call. Its structured next action goes through the existing validated executor, then the loop obtains a fresh frame. The local parser must match the whole command; “turn 90 if the path is clear” therefore stays closed-loop. Backboard persistence runs separately from movement decisions.

```sh
python3 main.py --goal "turn 360"
python3 main.py --goal "move forward 1.5 m"
python3 main.py --goal "move backward slightly"
python3 main.py --goal "stop"
```

`turn 360` becomes four `turn(90)` calls; `move forward 1.5 m` becomes two `forward(0.75)` calls. Signed turns use positive = left and negative = right. Numeric translations require metres (`m`, `meters`, or `metres`). “Slightly”, “a little”, and “a small amount” use `SLIGHT_TRANSLATION_M=0.2` and `SLIGHT_TURN_DEG=15` in `brain/direct_commands.py`. A trailing “then stop” appends a local `stop()` call: “move forward a small amount, then stop” stays DIRECT. Other compound or conditional commands still use CLOSED_LOOP. Gripper open/close, arm recenter, and explicit arm moves such as “move arm up 30 mm” also route directly. A spoken direct command overrides the current cycle; “stop” ends the active mission.

Direct mode does not visually check for obstacles between chunks. Chunk sizes come from the tool schemas (0.05–0.75 m, ±90°). Short remainders are redistributed to preserve the requested total; for example, 0.76 m becomes 0.71 + 0.05 m. Zero totals do nothing, totals below the translation minimum are rejected without moving, and `MAX_DIRECT_CHUNKS=100` rejects excessively large requests before execution. Logs report the mode, parsed command, requested total, chunk plan, individual commands, and total duration.

For four direct turn chunks, the fast path avoids all four multimodal decision calls and fresh-frame waits; only SDK command/completion time and physical movement remain. At 90°/s, 360° has a nominal rotation time of 4 seconds, plus acceleration and SDK overhead. This is an estimate, not a measured hardware benchmark.

The goal accompanies each multimodal decision alongside the current JPEG and local mission state. The planner can call bounded `forward`, `backward`, `strafe_left`, `strafe_right`, `turn`, `stop`, `move_arm`, `recenter_arm`, `open_gripper`, and `close_gripper` tools. Motion uses `ep.chassis.move(...).wait_for_completed()`; `stop` uses `ep.chassis.drive_speed(x=0, y=0, z=0)`.

Planner arguments are validated before execution: distances are clamped to 0.05–0.75 m, turns to ±90°, arm deltas to ±80 mm per axis, and speech to 240 characters. Missing/invalid arguments are logged and rejected without moving. Each response must contain one observation/target_visible/tool/args/goal_complete/finding object, with an optional boolean search_active. The entire response is validated before execution; malformed responses are logged verbatim and cause no movement. Each fresh frame authorizes at most one action. After a physical action, the next accepted frame must have arrived after that action finished. Failed camera/model reads block movement, and goal_complete=true requires a null tool and terminates the mission. Terminal logs include requested and clamped arguments, chassis action and xy/z speeds, duration, and rejection details.

Search history guides the planner without overriding its actions. `RobotState.search_active`, `search_direction` (+1 left / -1 right), and `search_rotation_deg` track completed, clamped search turns. Each decision also receives `relative_heading_deg` and the last 36 `inspected_viewpoints`, including pose, observation, and target visibility before each action. Headings are command-based estimates relative to the goal's starting view, not compass telemetry; a failed turn makes the estimate unknown. Rotation totals include revisited arcs and do not prove coverage. The planner should continue a useful search direction, but can adjust the camera, reposition, or reverse when evidence warrants it. There is no forced 60° turn or automatic termination at 360°. Detection ends active searching while preserving view history; a new goal resets that history. Completion is model-selected and stops further actions. DIRECT commands retain local decomposition without perception; direct turns update the heading estimate without claiming an inspected view.

The planner favors meaningful movements when the goal and view are clear, with finer corrections near people, obstacles, and targets. A poor camera view should be improved before navigating. Default chassis speeds are 0.7 m/s and 90°/s, configured by `DEFAULT_XY_SPEED_MPS` and `DEFAULT_Z_SPEED_DPS` in `control/robomaster.py`. Manual calls can still override speed; the physical smoke test retains its explicit slower 0.5 m/s translation default.

`get_state` exposes only telemetry received from the RoboMaster chassis. `get_obstacles` exposes raw onboard ToF readings in millimetres, with no inferred bearing.

The camera runs in a background reader at `STREAM_360P`, continuously draining `read_cv2_image(strategy="pipeline")` into a single latest-frame slot. `controller.start_camera()` starts that reader once without waiting for SDK startup; the first `get_latest_frame()` also starts it if needed. Later reads immediately return a copy of the buffered frame. Direct commands don't start the camera. There are no per-cycle SDK reads, retries, or warmup sleeps in perception.

`get_latest_frame()` returns `None` until a valid frame arrives and whenever its age exceeds `CAMERA_MAX_FRAME_AGE_S=1.0` in `control/robomaster.py`. The existing perception guard then skips vision, planning, and autonomous movement. A decode failure retains the last good frame without refreshing its timestamp. Short empty reads recover in the reader; two seconds without decoded frames or an invalid-data error triggers a stream restart there. Shutdown signals and joins the reader and stops the video stream. The standalone camera smoke test waits up to three seconds for its initial buffered frame.

Camera logs and `controller.get_camera_state()` expose `frame_age_s`, `last_frame_monotonic_s`, `decode_fps` (frames received during the preceding second), `decode_failures`, `stream_restarts`, and `reader_alive`. Frame timestamps measure local receipt from the SDK, not a camera-provided exposure timestamp. `CAMERA_READ_TIMEOUT_S`, `CAMERA_RESTART_AFTER_S`, and `CAMERA_RESTART_DELAY_S` configure reader recovery independently of the planner.

### Multimodal decisions and mission memory

CLOSED_LOOP uses `GEMINI_ACTION_MODEL=gemini-3.5-flash-lite` with the existing `GEMINI_API_KEY`. [Gemini 3.5 Flash-Lite supports image inputs and structured output](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite). One long-lived async Gemini client serves the application and closes during shutdown. The standalone `describe_scene()` and optional Backboard planner remain available for diagnostics/high-level use; neither runs in the per-movement path.

`RobotState` keeps the current goal, the last eight observations/actions, up to 24 significant findings, and relevant `mission_context`. Backboard receives the initial mission context, deduplicated findings, and local snapshots every ten valid decision cycles and at completion. A bounded background queue serializes these writes without awaiting them before action execution. Shutdown gives queued writes up to five seconds to drain; failed/overflowed writes are logged and local context remains available for the running mission. This queue is not a durable offline outbox. `brain.search_memory(query)` remains available for explicit, relevant retrieval; there is no unconditional historical-memory lookup per frame. Retrieved context can be supplied in `state.mission_context` when the task actually needs it.

Successful cycles have no unconditional sleep or vision minimum-interval throttle. Missing/unchanged frames wait 0.1 seconds for a new frame. Transient model/malformed-output failures back off from 0.5 seconds up to 8 seconds; rate limits honor the provider's retry delay. Five failed retries or exhausted daily quota stop the mission safely. A failure preserves the goal, prior observation/action results, findings, and pending spoken command. DIRECT never starts camera/inference/memory writes.

Each cycle logs frame age, multimodal latency, observation, selected tool/arguments, completion status, and executor duration. Backboard writes log their own latency separately. Older `GEMINI_VISION_*`, `VISION_MIN_INTERVAL_S`, and `BACKBOARD_*` model settings affect only the standalone diagnostic/high-level paths, not CLOSED_LOOP.

### Latency comparison

The reported old timings were approximately 1.5 seconds for vision plus 2.5–3 seconds for Backboard planning, before motion and the old successful-cycle sleep. The new critical path contains only the multimodal call and execution. If that call takes 1.5 seconds, removing the planner saves roughly 2.5–3 seconds of inference time per action; removing the unconditional one-second minimum gap saves additional time. The new model's combined image/action latency still needs a live measurement; this is an estimate, not a measured speedup.

A reproducible API-only benchmark is available:

```sh
python benchmark_closed_loop.py --samples 3
```

It sends the same synthetic 360p JPEG, goal, and internal planner/tool context to the configured services, compares the old two-call path with the new structured decision, and logs `BENCH` timings and medians. It never connects to a robot or executes selected tools. The comparison excludes motion and artificial sleeps. No live before/after measurements are claimed here. Offline tests cover SDK request serialization, single-action execution, fresh-frame guards, and non-blocking persistence.
