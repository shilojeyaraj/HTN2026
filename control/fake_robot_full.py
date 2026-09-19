"""
fake_robot_full.py -- Full-sensor Tier-0 simulator for the Hack the North rover.

Builds on fake_robot.py (same room, same movement verbs, same physics) and adds
the rest of the sensor suite listed in CLAUDE.md section 5's shared state, so
you can test how a brain reacts to more than just "there's a wall ahead". This
is a search-and-rescue rover, so the microphone is scripted around survivor
audio -- screams and calls for help -- not command words:

    camera          -- get_camera_frame()   (reuses obstacle detections as the
                                              vision-derived scene)
    temp sensor     -- get_temperature()    -> {celsius, status}
    microphone      -- get_audio()          -> {db, event}; event["kind"] is
                                                 "distress" (scream / call for
                                                 help -- what the detector API
                                                 would be listening for),
                                                 "sound" (hazard noise: rubble,
                                                 structural creak -- react with
                                                 caution, don't approach), or
                                                 "voice" (an operator command
                                                 word)
    gyro            -- get_gyro()           -> {pitch_deg, roll_deg, accel_z_g,
                                                 tipped, bump}
    motor encoder   -- get_encoder()        -> {left/right ticks, estimated vs
                                                 commanded velocity, slip_detected}
    everything      -- get_full_state()     -> all of the above + pose + sim time

NOTE: CLAUDE.md section 4 currently has ElevenLabs as voice-OUT (TTS) and
Baseten as voice-IN (STT). If ElevenLabs is what actually classifies distress
audio in the real stack, update CLAUDE.md's sponsor split to match -- this
file only shapes the simulated signal, not which API consumes it.

Events (distress calls, hazard noise, an operator command, a temp spike,
getting picked up, a wheel losing traction) are driven by a scripted timeline
of SensorEvent objects -- see build_events() below -- so a run is reproducible
and diffable, not puppeteered live. Edit build_events() to script your own
scenario.

demo_brain_full() is a stand-in policy showing the reaction you'd wire into
your real brain for each signal: turn toward and approach a distress call,
back away from hazard noise, stop on a "stop" command / tip / overheat, back
off on wheel slip, otherwise drive and dodge obstacles same as the Tier-0
demo. Replace it with your Backboard tick the same way fake_robot.py's
demo_brain() gets replaced -- call get_full_state(), send it to the brain,
execute whatever verbs come back.

Run it:
    python3 control/fake_robot_full.py             # live window
    python3 control/fake_robot_full.py --headless   # text trace + event/mission log
"""

import math
import random
import argparse
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from fake_robot import FakeRobot, Obstacle, RobotConfig, LiveViewer, _norm180, _HAS_MPL

if _HAS_MPL:
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, Wedge, Rectangle


# --------------------------------------------------------------------------- #
# Scripted sensor events
# --------------------------------------------------------------------------- #
@dataclass
class SensorEvent:
    t_start: float                       # sim seconds into the run
    kind: str                            # "sound" | "voice" | "temp" | "tip" | "wheel_slip"
    duration: float = 0.6                # seconds the event stays active
    value: dict = field(default_factory=dict)

    @property
    def t_end(self) -> float:
        return self.t_start + self.duration


@dataclass
class SensorConfig:
    ambient_temp_c: float = 22.0
    temp_noise_c: float = 0.15
    warm_c: float = 42.0
    overheat_c: float = 55.0
    ambient_db: float = 32.0
    mic_noise_db: float = 3.0
    gyro_noise_deg: float = 0.4
    wheelbase_m: float = 0.18
    ticks_per_meter: float = 800.0
    encoder_noise: float = 0.02          # fractional tick noise
    slip_factor: float = 0.35            # ticks reported vs true, on the slipping wheel


# --------------------------------------------------------------------------- #
# The full-sensor robot
# --------------------------------------------------------------------------- #
class FullFakeRobot(FakeRobot):
    def __init__(self, *args, events: Optional[List[SensorEvent]] = None,
                 sensors: Optional[SensorConfig] = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.sensors = sensors or SensorConfig()
        self.events = sorted(events or [], key=lambda e: e.t_start)
        self.t = 0.0
        self._active: Dict[str, SensorEvent] = {}
        self._last_pose = (self.x, self.y, self.theta)
        self._last_step_ticks = (0.0, 0.0)
        self._ticks_l_total = 0.0
        self._ticks_r_total = 0.0
        self.event_log: List[str] = []
        self.mission_log: List[str] = []
        self._audio_queue: List[dict] = []

    # ---- internal: advance sim clock, events and wheel encoders ---- #
    _AUDIO_KINDS = ("distress", "voice", "sound")

    def _format_audio_event(self, ev: "SensorEvent") -> dict:
        if ev.kind == "distress":
            return {"kind": "distress", "label": ev.value.get("label", "call_for_help"),
                    "text": ev.value.get("text", ""), "bearing_deg": ev.value.get("bearing_deg", 0.0),
                    "db_boost": ev.value.get("db_boost", 30.0)}
        if ev.kind == "voice":
            return {"kind": "voice", "text": ev.value.get("text", ""),
                    "bearing_deg": ev.value.get("bearing_deg", 0.0), "db_boost": ev.value.get("db_boost", 25.0)}
        return {"kind": "sound", "label": ev.value.get("label", "hazard_noise"),
                "bearing_deg": ev.value.get("bearing_deg", 0.0), "db_boost": ev.value.get("db_boost", 30.0)}

    def _advance(self):
        self.t += self.cfg.dt
        for ev in self.events:
            active_now = ev.t_start <= self.t <= ev.t_end
            was_active = self._active.get(ev.kind) is ev
            if active_now and not was_active:
                self._active[ev.kind] = ev
                self.event_log.append(f"[t={self.t:5.2f}s] EVENT {ev.kind} -> {ev.value}")
                # audio is edge-triggered and queued, not polled: a scream
                # shorter than the brain's decision cycle must still reach it
                if ev.kind in self._AUDIO_KINDS:
                    self._audio_queue.append(self._format_audio_event(ev))
            elif not active_now and was_active:
                del self._active[ev.kind]

        lx, ly, lth = self._last_pose
        dx, dy = self.x - lx, self.y - ly
        dist = math.hypot(dx, dy)
        th = math.radians(self.theta)
        signed_dist = dist if (dx * math.cos(th) + dy * math.sin(th)) >= 0 else -dist
        dtheta = math.radians(_norm180(self.theta - lth))
        wb = self.sensors.wheelbase_m
        left_m = signed_dist - dtheta * wb / 2
        right_m = signed_dist + dtheta * wb / 2

        slip_ev = self._active.get("wheel_slip")
        slip_side = slip_ev.value.get("side", "l") if slip_ev else None
        ticks = {}
        for side, meters in (("l", left_m), ("r", right_m)):
            noisy = meters * (1 + random.uniform(-self.sensors.encoder_noise, self.sensors.encoder_noise))
            if slip_side == side:
                noisy *= self.sensors.slip_factor
            ticks[side] = noisy * self.sensors.ticks_per_meter
        self._ticks_l_total += ticks["l"]
        self._ticks_r_total += ticks["r"]
        self._last_step_ticks = (ticks["l"], ticks["r"])
        self._last_pose = (self.x, self.y, self.theta)

    def _emit(self):
        self._advance()
        super()._emit()

    # ---- read side: sensors ---- #
    def get_camera_frame(self) -> dict:
        return {"frame_id": round(self.t / self.cfg.dt), "objects": self.get_detections()}

    def get_temperature(self) -> dict:
        ev = self._active.get("temp")
        spike = ev.value.get("delta_c", 0.0) if ev else 0.0
        temp = (self.sensors.ambient_temp_c + spike
                + random.uniform(-self.sensors.temp_noise_c, self.sensors.temp_noise_c))
        status = ("overheat" if temp >= self.sensors.overheat_c else
                  "warm" if temp >= self.sensors.warm_c else "ok")
        return {"celsius": round(temp, 1), "status": status}

    def get_audio(self) -> dict:
        """Consumes the queue (FIFO): each call delivers at most one detection,
        exactly once, regardless of how the polling cadence lines up against
        the event's duration. Use peek_audio() for display-only reads."""
        db = self.sensors.ambient_db + random.uniform(-self.sensors.mic_noise_db, self.sensors.mic_noise_db)
        event = None
        if self._audio_queue:
            event = dict(self._audio_queue.pop(0))
            db += event.pop("db_boost", 0.0)
        return {"db": round(db, 1), "event": event}

    def peek_audio(self) -> dict:
        """Read-only ambient level + currently-active kind, for a display loop
        that must not steal detections meant for the brain's get_audio()."""
        active_kind = next((k for k in self._AUDIO_KINDS if k in self._active), None)
        return {"db": round(self.sensors.ambient_db, 1), "active": active_kind}

    def get_gyro(self) -> dict:
        pitch = random.uniform(-self.sensors.gyro_noise_deg, self.sensors.gyro_noise_deg)
        roll = random.uniform(-self.sensors.gyro_noise_deg, self.sensors.gyro_noise_deg)
        accel_z = 1.0 + random.uniform(-0.01, 0.01)   # resting gravity, in g
        tip_ev = self._active.get("tip")
        bump_ev = self._active.get("bump")
        if tip_ev:
            pitch += tip_ev.value.get("pitch_deg", 70.0)
        if bump_ev:
            accel_z += bump_ev.value.get("accel_spike_g", 1.2)
        return {"pitch_deg": round(pitch, 1), "roll_deg": round(roll, 1),
                "accel_z_g": round(accel_z, 2),
                "tipped": abs(pitch) > 45.0, "bump": bump_ev is not None}

    def get_encoder(self) -> dict:
        lt, rt = self._last_step_ticks
        v = (lt + rt) / 2 / self.sensors.ticks_per_meter / self.cfg.dt if self.cfg.dt else 0.0
        # approximation: "commanded" only tracks whether a move verb is in
        # flight, not its exact target speed profile -- good enough to spot
        # a commanded-vs-measured mismatch (stall/slip), not to reconstruct it
        commanded = 0.0 if self.last_status in ("stopped", "stopped_by_obstacle") else self.cfg.max_speed
        return {"left_ticks_total": round(self._ticks_l_total), "right_ticks_total": round(self._ticks_r_total),
                "estimated_velocity_mps": round(v, 3), "commanded_velocity_mps": round(commanded, 3),
                "slip_detected": "wheel_slip" in self._active}

    def get_full_state(self) -> dict:
        return {
            "t": round(self.t, 2),
            "pose": self.get_state(),
            "camera": self.get_camera_frame(),
            "temperature": self.get_temperature(),
            "audio": self.get_audio(),
            "gyro": self.get_gyro(),
            "encoder": self.get_encoder(),
        }


# --------------------------------------------------------------------------- #
# Live viewer with a sensor readout panel
# --------------------------------------------------------------------------- #
class FullLiveViewer(LiveViewer):
    def update(self, robot: FullFakeRobot):
        self._frame += 1
        if self._frame % 2 != 0:
            return
        ax = self.ax
        ax.clear()
        ax.set_xlim(0, robot.W)
        ax.set_ylim(0, robot.H)
        ax.set_aspect("equal")
        ax.set_title(f"pose=({robot.x:.2f}, {robot.y:.2f}, {robot.theta:.0f} deg)"
                     f"   status={robot.last_status}   t={robot.t:5.1f}s")
        ax.add_patch(Rectangle((0, 0), robot.W, robot.H, fill=False, lw=2))
        for o in robot.obstacles:
            ax.add_patch(Circle((o.x, o.y), o.r, color="0.4"))
        ax.add_patch(Wedge((robot.x, robot.y), robot.cfg.sensor_range,
                           robot.theta - robot.cfg.sensor_fov / 2,
                           robot.theta + robot.cfg.sensor_fov / 2,
                           color="tab:blue", alpha=0.08))
        if len(robot.trail) > 1:
            xs, ys = zip(*robot.trail)
            ax.plot(xs, ys, "-", color="tab:blue", alpha=0.5, lw=1)
        ax.add_patch(Circle((robot.x, robot.y), robot.cfg.radius, color="tab:blue"))
        th = math.radians(robot.theta)
        ax.plot([robot.x, robot.x + 0.3 * math.cos(th)],
                [robot.y, robot.y + 0.3 * math.sin(th)], "-", color="white", lw=2)

        # peek-only reads here: get_audio() consumes a one-shot queue meant
        # for the brain, and this display loop must not steal from it
        temp = robot.get_temperature()
        gyro = robot.get_gyro()
        encoder = robot.get_encoder()
        audio = robot.peek_audio()
        lines = [
            f"temp   {temp['celsius']:5.1f}C  [{temp['status']}]",
            f"mic    {audio['db']:5.1f}dB" + (f"  <- {audio['active']}" if audio["active"] else ""),
            f"gyro   pitch={gyro['pitch_deg']:5.1f}  roll={gyro['roll_deg']:5.1f}"
            + ("  TIPPED" if gyro["tipped"] else ""),
            f"enc    L={encoder['left_ticks_total']:.0f} R={encoder['right_ticks_total']:.0f}"
            + ("  SLIP" if encoder["slip_detected"] else ""),
        ]
        flagged = temp["status"] == "overheat" or gyro["tipped"] or encoder["slip_detected"]
        ax.text(0.02, 0.98, "\n".join(lines), transform=ax.transAxes,
                va="top", ha="left", fontsize=8, family="monospace",
                color="tab:red" if flagged else "0.9",
                bbox=dict(facecolor="black", alpha=0.6, pad=4))
        plt.pause(0.001)


# --------------------------------------------------------------------------- #
# A stand-in brain that reacts to every sensor, not just obstacles.
# --------------------------------------------------------------------------- #
def demo_brain_full(robot: FullFakeRobot, ticks: int = 400):
    for _ in range(ticks):
        full = robot.get_full_state()
        gyro, temp, audio, encoder = full["gyro"], full["temperature"], full["audio"], full["encoder"]

        if gyro["tipped"]:
            robot.stop()
            continue
        if temp["status"] == "overheat":
            robot.stop()
            continue
        if audio["event"] and audio["event"]["kind"] == "distress":
            bearing = audio["event"]["bearing_deg"]
            robot.mission_log.append(
                f"[t={full['t']:5.2f}s] SURVIVOR DETECTED ({audio['event']['label']}) "
                f"\"{audio['event']['text']}\" bearing={bearing:+.0f}deg -> approaching")
            robot.turn(bearing)      # face the source
            robot.forward(0.3)       # close distance toward it
            continue
        if audio["event"] and audio["event"]["kind"] == "voice" and "stop" in audio["event"]["text"].lower():
            robot.stop()
            continue
        if audio["event"] and audio["event"]["kind"] == "sound":
            bearing = audio["event"]["bearing_deg"]
            robot.mission_log.append(
                f"[t={full['t']:5.2f}s] HAZARD NOISE ({audio['event']['label']}) "
                f"bearing={bearing:+.0f}deg -> backing away")
            robot.turn(-30 if bearing > 0 else 30)   # startle-turn away from the hazard
            continue
        if encoder["slip_detected"]:
            robot.backward(0.2)
            robot.turn(45)
            continue

        dets = full["camera"]["objects"]
        ahead = [d for d in dets if abs(d["bearing_deg"]) < 30]
        blocked = ahead and min(d["edge_distance"] for d in ahead) < 0.6
        if blocked:
            left = sum(1 for d in dets if d["bearing_deg"] > 0)
            right = sum(1 for d in dets if d["bearing_deg"] < 0)
            robot.turn(50 if right >= left else -50)
        else:
            res = robot.forward(0.3)
            if res["status"] == "stopped_by_obstacle":
                robot.turn(50)


def build_events() -> List[SensorEvent]:
    """Edit this to script your own test scenario (times are sim seconds).

    Modeled as a search-and-rescue sweep: "distress" events are what the real
    audio-detector API listens for (screams, calls for help), while "sound"
    events are hazard noise -- rubble, structural creaks -- the robot should
    treat with caution rather than approach.
    """
    return [
        SensorEvent(t_start=2.0, kind="distress", duration=0.6,
                    value={"label": "scream", "text": "", "bearing_deg": -25, "db_boost": 32}),
        SensorEvent(t_start=8.0, kind="distress", duration=1.0,
                    value={"label": "call_for_help", "text": "help! is anyone there?",
                           "bearing_deg": 55, "db_boost": 28}),
        SensorEvent(t_start=13.0, kind="sound", duration=0.4,
                    value={"label": "structural_creak", "bearing_deg": 15, "db_boost": 30}),
        SensorEvent(t_start=17.0, kind="voice", duration=0.5,
                    value={"text": "stop", "bearing_deg": 0, "db_boost": 18}),   # operator override
        SensorEvent(t_start=20.0, kind="temp", duration=4.0,
                    value={"delta_c": 38.0}),          # ambient 22C + 38 -> overheat
        SensorEvent(t_start=26.0, kind="tip", duration=1.0,
                    value={"pitch_deg": 70.0}),         # picked up / tipped over
        SensorEvent(t_start=30.0, kind="wheel_slip", duration=3.0,
                    value={"side": "l"}),               # rubble underfoot
    ]


def build_room() -> FullFakeRobot:
    """Edit this to match your demo space."""
    obstacles = [
        Obstacle(1.6, 1.1, 0.28),
        Obstacle(2.6, 2.1, 0.30),
        Obstacle(3.2, 0.8, 0.22),
        Obstacle(1.0, 2.3, 0.22),
    ]
    return FullFakeRobot(room=(4.0, 3.0), obstacles=obstacles, start=(0.4, 0.4, 30.0),
                          events=build_events())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--headless", action="store_true",
                    help="run without a window and print a text trace")
    ap.add_argument("--ticks", type=int, default=400,
                    help="brain decision ticks (each covers a verb call, i.e. many sim-seconds or a fraction of one)")
    args = ap.parse_args()

    robot = build_room()

    if args.headless or not _HAS_MPL:
        robot.cfg.realtime = False

        def trace(r):
            trace.n += 1
            if trace.n % 10 == 0:
                # peek-only reads: get_audio() consumes the brain's queue
                temp, gyro, encoder = r.get_temperature(), r.get_gyro(), r.get_encoder()
                audio = r.peek_audio()
                print(f"  t={r.t:6.2f}s  {r.get_state()}  status={r.last_status:20s}  "
                      f"temp={temp['celsius']:5.1f}C  mic={audio['db']:5.1f}dB  "
                      f"tipped={gyro['tipped']}  slip={encoder['slip_detected']}")
        trace.n = 0
        robot.step_callback = trace
        print("Running headless full-sensor sim...")
        demo_brain_full(robot, ticks=args.ticks)
        print("Event log:")
        for line in robot.event_log:
            print(" ", line)
        print("Mission log:")
        for line in robot.mission_log:
            print(" ", line)
        print(f"Done. final={robot.get_state()} status={robot.last_status} "
              f"trail_points={len(robot.trail)}")
        return

    viewer = FullLiveViewer(robot)
    robot.step_callback = viewer.update
    demo_brain_full(robot, ticks=args.ticks)
    print("Demo finished. Close the window to exit.")
    print("Event log:")
    for line in robot.event_log:
        print(" ", line)
    print("Mission log:")
    for line in robot.mission_log:
        print(" ", line)
    plt.ioff()
    plt.show()


if __name__ == "__main__":
    main()
