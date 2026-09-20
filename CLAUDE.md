# Project context

This repository controls a DJI RoboMaster EP Core from a Linux laptop connected to the robot's AP Wi-Fi.

`control/robomaster.py` is the sole RoboMaster SDK boundary. It creates one `robot.Robot`, initializes it with `conn_type="ap"`, owns chassis/camera lifecycle, and closes the connection. No planner, tool, or perception module may import `robomaster` directly.

Movement tools are bounded `forward(distance_m)`, `backward(distance_m)`, `strafe_left(distance_m)`, `strafe_right(distance_m)`, `turn(degrees)`, and `stop()`. They are registered in `brain/tools.py` and dispatched in `brain/loop.py`. Discrete movement uses `chassis.move(...).wait_for_completed()`; emergency stop uses `chassis.drive_speed(x=0, y=0, z=0)`.

The RoboMaster camera starts once at 360p and `get_latest_frame()` retries transient failures before returning `None`. Gemini vision receives a JPEG through `perception/camera.py`. Chassis state and ToF readings come from SDK subscriptions; ToF values are raw millimetres with no inferred direction.

Backboard remains the deliberative planner, Baseten remains the optional command parser/STT provider, and ElevenLabs remains TTS. These services stay outside the hardware boundary.
