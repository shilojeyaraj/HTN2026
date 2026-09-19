---
name: add-movement-verb
description: Contract for adding or changing any robot movement capability. Use this whenever adding, editing, or extending a movement verb, action, or tool the brain can call to move the robot (forward, backward, turn, drive, dock, follow, approach, patrol, etc.), or when editing the movement tool schema, the controller, or the verb handlers. Trigger it even if the user only says "add a way for the robot to X", "give the robot a new move", or "let the agent do Y". Every new or changed verb must follow this contract.
---

# Add or change a movement verb

Every movement capability the brain can call must follow this contract, so a new verb cannot quietly break the two-loop safety design. Source of truth is CLAUDE.md section 6.

## Contract (all required)

1. **Bounded and self-completing.** The verb performs a finite action and then stops on its own. No open-ended continuous motion. Example: `forward(0.5)` drives about 0.5 m and stops. Prefer distance or angle arguments over "start moving" semantics.
2. **Returns a status.** Every verb returns a dict the brain can reason on: `{"status": "completed" | "stopped_by_obstacle" | "error", ...}` with distance or clearance where relevant. This is the feedback loop the brain plans against. Never return `None` silently.
3. **Intent only, never motors.** The verb sends intent to the arbiter/controller. It NEVER publishes to motors or `/cmd_vel` directly. The reflex loop must still be able to veto it.
4. **Reflex-safe.** Any forward motion respects the reflex clearance / safety distance and halts when the reflex loop says stop. A verb can never override an emergency stop.
5. **Small, stable schema.** Only add a new verb if existing verbs cannot compose the behavior. Prefer composition (`forward` + `turn`) over a new primitive. A bloated verb set makes the brain worse, not better.
6. **Registered as a Backboard tool.** Give it a clear name, a one-line description, and typed arguments so the planner can call it reliably. Keep the fixed tool schema at the top of the prompt for caching.
7. **Mirrored in the sim.** Add or update the verb in `fake_robot.py` with the same signature and status contract, and test it there before it touches hardware.
8. **Consistent naming and units.** Match the existing verbs (`forward`, `backward`, `turn`, `stop`, `speak`). Distances in metres, angles in degrees (+ left, - right).

## Reference

- **Verb to velocity:** the controller maps the verb to a `Twist` (`linear.x` forward/back, `angular.z` turn), then to wheels via differential-drive kinematics: `left = linear.x - angular.z * wheelbase/2`, `right = linear.x + angular.z * wheelbase/2`.
- **Read side:** perception verbs (`get_state`, `get_detections`) are how the brain senses. Keep them separate from movement verbs; they do not move the robot and do not go through the arbiter.

## Template

```python
def approach(self, distance_m: float) -> dict:
    """Move forward up to distance_m, stopping early if blocked. Bounded, reflex-safe."""
    # Delegate to the same bounded, reflex-checked translate that forward() uses.
    return self._translate(abs(distance_m), direction=+1)
```

## After writing the verb

1. Register it as a Backboard tool (name, description, typed args).
2. Mirror it in `fake_robot.py` and run it in the simulator.
3. Run the `safety-review` skill before merging.
