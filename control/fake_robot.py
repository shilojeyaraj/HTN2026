"""
fake_robot.py -- Tier-0 driving simulator for the Hack the North rover.

Point your brain at this and watch it drive, with no chassis and no GPU.

It exposes the SAME movement verbs your real controller will (see CLAUDE.md
section 6), so the brain code is identical against sim vs hardware. Swapping
to the real robot means changing what lives behind these verbs, nothing above.

  Verbs (bounded, self-completing, return a status dict):
    robot.forward(distance_m)   -> drives forward, stops early on obstacle
    robot.backward(distance_m)
    robot.turn(degrees)         -> + is left, - is right
    robot.stop()
  Read side (what perception feeds the brain):
    robot.get_state()           -> {x, y, heading_deg}
    robot.get_detections()      -> [{distance, bearing_deg, edge_distance}, ...]
    robot.reflex_clearance()    -> metres of clear space straight ahead

The reflex stop is built into forward(): if an obstacle enters the safety
distance, the move halts and returns status "stopped_by_obstacle". That models
the reflex loop winning over the brain, and the returned status is the
Inner-Monologue feedback the brain reasons on next tick.

Run it:
    python fake_robot.py            # live window, watch the demo brain drive
    python fake_robot.py --headless # no window, prints a text trace (for CI)

Plug your real brain in: replace demo_brain() with your Backboard tick. Call
get_detections()/get_state(), send them to the brain, and execute whatever
verbs it returns. The rest of this file does not change.
"""

import math
import time
import argparse
from dataclasses import dataclass, field
from typing import Callable, List, Optional

try:
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Wedge, Rectangle
    _HAS_MPL = True
except Exception:
    _HAS_MPL = False


# --------------------------------------------------------------------------- #
# World
# --------------------------------------------------------------------------- #
@dataclass
class Obstacle:
    x: float
    y: float
    r: float = 0.25


@dataclass
class RobotConfig:
    radius: float = 0.15        # robot footprint radius (m)
    max_speed: float = 0.4      # m/s
    turn_rate: float = 120.0    # deg/s
    dt: float = 0.05            # seconds per micro-step
    safety_dist: float = 0.30   # reflex stop distance ahead (m)
    sensor_range: float = 2.5   # detection range (m)
    sensor_fov: float = 120.0   # total field of view (deg)
    realtime: bool = True       # sleep dt each step so motion is watchable


def _norm180(a: float) -> float:
    """Wrap an angle in degrees to [-180, 180]."""
    return (a + 180.0) % 360.0 - 180.0


# --------------------------------------------------------------------------- #
# The fake robot
# --------------------------------------------------------------------------- #
class FakeRobot:
    def __init__(self, room=(4.0, 3.0), obstacles: Optional[List[Obstacle]] = None,
                 start=(0.5, 0.5, 0.0), config: Optional[RobotConfig] = None):
        self.W, self.H = room
        self.obstacles = obstacles or []
        self.x, self.y, self.theta = start          # theta in degrees
        self.cfg = config or RobotConfig()
        self.trail = [(self.x, self.y)]
        self.last_status = "ready"
        self.step_callback: Optional[Callable[["FakeRobot"], None]] = None

    # ---- internal ---- #
    def _emit(self):
        """Advance one visual/timing tick: redraw if a viewer is attached."""
        if self.step_callback:
            self.step_callback(self)
        if self.cfg.realtime:
            time.sleep(self.cfg.dt)

    def _collides(self, x: float, y: float) -> bool:
        r = self.cfg.radius
        if not (r <= x <= self.W - r and r <= y <= self.H - r):
            return True
        for o in self.obstacles:
            if math.hypot(o.x - x, o.y - y) < (r + o.r):
                return True
        return False

    def reflex_clearance(self) -> float:
        """Clear distance straight ahead before the footprint would hit something."""
        th = math.radians(self.theta)
        hx, hy = math.cos(th), math.sin(th)
        best = self.cfg.sensor_range
        # obstacles: project onto heading, keep those roughly in our path
        for o in self.obstacles:
            dx, dy = o.x - self.x, o.y - self.y
            along = dx * hx + dy * hy
            if along <= 0:
                continue
            perp = abs(-dx * hy + dy * hx)
            if perp < self.cfg.radius + o.r:
                best = min(best, along - (self.cfg.radius + o.r))
        # walls
        if hx > 1e-6:
            best = min(best, (self.W - self.cfg.radius - self.x) / hx)
        elif hx < -1e-6:
            best = min(best, (self.cfg.radius - self.x) / hx)
        if hy > 1e-6:
            best = min(best, (self.H - self.cfg.radius - self.y) / hy)
        elif hy < -1e-6:
            best = min(best, (self.cfg.radius - self.y) / hy)
        return max(0.0, best)

    # ---- read side (perception) ---- #
    def get_state(self) -> dict:
        return {"x": round(self.x, 3), "y": round(self.y, 3),
                "heading_deg": round(self.theta % 360, 1)}

    def get_detections(self) -> List[dict]:
        """Obstacles within range and field of view, as distance + bearing."""
        out = []
        for o in self.obstacles:
            dx, dy = o.x - self.x, o.y - self.y
            dist = math.hypot(dx, dy)
            if dist > self.cfg.sensor_range:
                continue
            bearing = _norm180(math.degrees(math.atan2(dy, dx)) - self.theta)
            if abs(bearing) > self.cfg.sensor_fov / 2:
                continue
            out.append({"distance": round(dist, 3),
                        "bearing_deg": round(bearing, 1),
                        "edge_distance": round(max(0.0, dist - o.r), 3)})
        return sorted(out, key=lambda d: d["distance"])

    # ---- movement verbs ---- #
    def forward(self, distance_m: float) -> dict:
        return self._translate(abs(distance_m), +1)

    def backward(self, distance_m: float) -> dict:
        return self._translate(abs(distance_m), -1)

    def _translate(self, target: float, direction: int) -> dict:
        step = self.cfg.max_speed * self.cfg.dt
        traveled = 0.0
        th = math.radians(self.theta)
        while traveled < target:
            # reflex stop only applies to forward motion
            if direction > 0 and self.reflex_clearance() <= self.cfg.safety_dist:
                self.last_status = "stopped_by_obstacle"
                self._emit()
                return {"status": "stopped_by_obstacle",
                        "distance_traveled": round(traveled, 3),
                        "clearance": round(self.reflex_clearance(), 3)}
            d = min(step, target - traveled)
            nx = self.x + direction * d * math.cos(th)
            ny = self.y + direction * d * math.sin(th)
            if self._collides(nx, ny):
                self.last_status = "stopped_by_obstacle"
                self._emit()
                return {"status": "stopped_by_obstacle",
                        "distance_traveled": round(traveled, 3), "reason": "collision"}
            self.x, self.y = nx, ny
            traveled += d
            self.trail.append((self.x, self.y))
            self._emit()
        self.last_status = "completed"
        return {"status": "completed", "distance_traveled": round(traveled, 3)}

    def turn(self, degrees: float) -> dict:
        step = self.cfg.turn_rate * self.cfg.dt
        turned = 0.0
        direction = 1 if degrees >= 0 else -1
        target = abs(degrees)
        while turned < target:
            d = min(step, target - turned)
            self.theta = (self.theta + direction * d) % 360
            turned += d
            self._emit()
        self.last_status = "completed"
        return {"status": "completed", "degrees_turned": round(direction * turned, 1)}

    def stop(self) -> dict:
        self.last_status = "stopped"
        self._emit()
        return {"status": "stopped"}


# --------------------------------------------------------------------------- #
# Live viewer (optional; needs matplotlib + a display)
# --------------------------------------------------------------------------- #
class LiveViewer:
    def __init__(self, robot: FakeRobot):
        self.robot = robot
        plt.ion()
        self.fig, self.ax = plt.subplots(figsize=(6, 4.5))
        self.fig.canvas.manager.set_window_title("Tier-0 rover sim")
        self._frame = 0

    def update(self, robot: FakeRobot):
        # throttle redraws so the sim stays smooth
        self._frame += 1
        if self._frame % 2 != 0:
            return
        ax = self.ax
        ax.clear()
        ax.set_xlim(0, robot.W)
        ax.set_ylim(0, robot.H)
        ax.set_aspect("equal")
        ax.set_title(f"pose=({robot.x:.2f}, {robot.y:.2f}, {robot.theta:.0f} deg)"
                     f"   status={robot.last_status}")
        # room + obstacles
        ax.add_patch(Rectangle((0, 0), robot.W, robot.H, fill=False, lw=2))
        for o in robot.obstacles:
            ax.add_patch(Circle((o.x, o.y), o.r, color="0.4"))
        # sensor cone
        ax.add_patch(Wedge((robot.x, robot.y), robot.cfg.sensor_range,
                           robot.theta - robot.cfg.sensor_fov / 2,
                           robot.theta + robot.cfg.sensor_fov / 2,
                           color="tab:blue", alpha=0.08))
        # trail
        if len(robot.trail) > 1:
            xs, ys = zip(*robot.trail)
            ax.plot(xs, ys, "-", color="tab:blue", alpha=0.5, lw=1)
        # robot + heading
        ax.add_patch(Circle((robot.x, robot.y), robot.cfg.radius, color="tab:blue"))
        th = math.radians(robot.theta)
        ax.plot([robot.x, robot.x + 0.3 * math.cos(th)],
                [robot.y, robot.y + 0.3 * math.sin(th)], "-", color="white", lw=2)
        plt.pause(0.001)


# --------------------------------------------------------------------------- #
# A stand-in brain. Replace this with your Backboard tick.
# --------------------------------------------------------------------------- #
def demo_brain(robot: FakeRobot, ticks: int = 60):
    """
    A dumb reactive policy so you can watch the sim drive immediately.

    This is exactly where your real brain plugs in: instead of the if/else
    below, send get_detections()/get_state() to Backboard and execute the
    tool calls it returns. The verb calls stay identical.
    """
    for _ in range(ticks):
        dets = robot.get_detections()
        ahead = [d for d in dets if abs(d["bearing_deg"]) < 30]
        blocked = ahead and min(d["edge_distance"] for d in ahead) < 0.6

        if blocked:
            # turn toward whichever side has more open space
            left = sum(1 for d in dets if d["bearing_deg"] > 0)
            right = sum(1 for d in dets if d["bearing_deg"] < 0)
            robot.turn(50 if right >= left else -50)
        else:
            res = robot.forward(0.5)
            if res["status"] == "stopped_by_obstacle":
                robot.turn(50)


def build_room() -> FakeRobot:
    """Edit this to match your demo space."""
    obstacles = [
        Obstacle(1.6, 1.1, 0.28),
        Obstacle(2.6, 2.1, 0.30),
        Obstacle(3.2, 0.8, 0.22),
        Obstacle(1.0, 2.3, 0.22),
    ]
    return FakeRobot(room=(4.0, 3.0), obstacles=obstacles, start=(0.4, 0.4, 30.0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true",
                    help="run without a window and print a text trace")
    ap.add_argument("--ticks", type=int, default=60)
    args = ap.parse_args()

    robot = build_room()

    if args.headless or not _HAS_MPL:
        robot.cfg.realtime = False
        # print a compact trace so you can verify logic in CI
        def trace(r):
            trace.n += 1
            if trace.n % 10 == 0:
                print(f"  step {trace.n:4d}  {r.get_state()}  {r.last_status}")
        trace.n = 0
        robot.step_callback = trace
        print("Running headless...")
        demo_brain(robot, ticks=args.ticks)
        print(f"Done. final={robot.get_state()} status={robot.last_status} "
              f"trail_points={len(robot.trail)}")
        return

    viewer = LiveViewer(robot)
    robot.step_callback = viewer.update
    demo_brain(robot, ticks=args.ticks)
    print("Demo finished. Close the window to exit.")
    plt.ioff()
    plt.show()


if __name__ == "__main__":
    main()
