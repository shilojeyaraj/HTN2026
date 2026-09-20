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

With clear space around the robot, run:

```sh
python3 robomaster_smoke_test.py
```

By default, the script recentres the arm, moves it 40 mm forward and 30 mm up, opens and closes the gripper at low power, captures a frame from that view, then recentres the arm. It always pauses the gripper and closes the SDK connection.

Chassis motion is opt-in: add `--exercise-chassis` to move forward 0.2 m and turn 30°, or `--exercise-chassis --spin-degrees 360` for one full chassis spin. Every movement value is configurable.

## Agent runtime

```sh
python3 main.py --goal "Explore this room in small steps and report people or hazards."
```

The goal accompanies each planner decision alongside the latest scene description. The planner can call bounded `forward`, `backward`, `strafe_left`, `strafe_right`, `turn`, `stop`, `move_arm`, `recenter_arm`, `open_gripper`, and `close_gripper` tools. Motion uses `ep.chassis.move(...).wait_for_completed()`; `stop` uses `ep.chassis.drive_speed(x=0, y=0, z=0)`.

`get_state` exposes only telemetry received from the RoboMaster chassis. `get_obstacles` exposes raw onboard ToF readings in millimetres, with no inferred bearing. Camera frames come from the RoboMaster stream at 360p and are retried when a transient read returns no frame.
