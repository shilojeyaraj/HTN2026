---
name: add-movement-verb
description: Contract for changing a RoboMaster movement tool the planner can call.
---

# Add or change a movement verb

1. Keep each tool bounded and self-completing. Distances use metres; turns use degrees.
2. Return `{"status": "completed"}` or an error result the planner can reason about.
3. Add the schema to `brain/tools.py` and route it through `brain/loop.py`.
4. Implement SDK work only in `control/robomaster.py`, using `chassis.move(...).wait_for_completed()`.
5. Test its coordinates and failure-stop behavior with a mocked RoboMaster controller. Do not add GPIO, wheel, encoder, or simulator compatibility code.
