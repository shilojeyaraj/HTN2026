# Camera Integration Gap Analysis

The gap between the new Pi CSI + laptop depth pipeline and the existing
agent brain architecture, how we bridge it, and the potential effects.

---

## What changed

The original architecture assumed an **OAK-D S2** camera: on-device depth,
on-device object detection (YOLO), and absolute distance in meters. The
`Detection` type was designed around this: `{label, bbox, distance_m, bearing_deg}`.

The actual hardware is a **Pi 5 with a CSI camera** and no OAK-D, no LiDAR.
A teammate built a pipeline where the Pi streams JPEG frames over Wi-Fi to
a laptop running **Depth-Anything-V2-Small** (monocular relative depth).
The laptop returns proximity scores for left/center/right regions, not
absolute distances or object labels.

---

## The gap

| What the brain expects | What the new pipeline provides |
|------------------------|-------------------------------|
| `Detection` with `label` (e.g. "chair") | No object labels — only "obstacle" (generic) |
| `Detection` with `distance_m` (absolute meters) | Relative proximity scores 0-1 (higher = nearer) |
| `Detection` with `bbox` (pixel coords) | No bbox — only region (left/center/right third) |
| `Detection` with `bearing_deg` (exact angle) | Approximate: -30°, 0°, +30° for left/center/right |
| Detections at 30 Hz (for reflex loop) | Depth at ~1-5 Hz (laptop inference rate over Wi-Fi) |
| On-device, no network dependency | Requires Wi-Fi to laptop for depth |

---

## How we bridge it

`perception/camera.py` is rewritten as a **TCP bridge**:

1. Captures CSI frames via `rpicam-vid` (same as `pi/client.py`)
2. Stores latest JPEG in a thread-safe buffer (for Gemini vision)
3. Sends frames to the laptop depth server over TCP
4. Receives depth results back and stores them
5. Converts proximity scores to pseudo-`Detection` objects:
   - `distance_m = 1.0 - proximity_score` (monotonic, not true meters)
   - `bearing_deg`: left=-30, center=0, right=+30
   - `label`: "obstacle"
   - `bbox`: (0,0,0,0) — no pixel coordinates from monocular depth
6. Exposes the same `get_latest_frame()` and `get_latest_detections()` interface

The brain, reflex loop, safety gate, and controller are **unchanged** — they
still call the same functions and get the same `Detection` type.

---

## Potential effects

### 1. Safety: reflex loop may be slower to react

**Before:** OAK-D depth at 30 Hz → reflex loop checks obstacles every 33ms.
**After:** Laptop depth at ~1-5 Hz → reflex loop still runs at 30 Hz, but
detections update only when a new depth result arrives (every 200ms-1s).

**Risk:** An obstacle could appear between depth updates and the reflex loop
won't know for up to 1 second. At 0.3 m/s driving speed, that's up to 30cm
of travel before the reflex loop reacts.

**Mitigation:** Drive slower (0.15 m/s) until we add a faster onboard
depth source. The watchdog still halts the robot if the brain stops sending
commands. The reflex loop still wins at the arbiter when it does have data.

### 2. Pseudo-distance is not real distance

**Before:** `distance_m` was absolute meters from stereo depth.
**After:** `distance_m = 1.0 - proximity_score` is a monotonic mapping of
relative depth. A score of 0.8 → distance 0.2 (close), 0.3 → distance 0.7 (far).
But 0.2 is not 20cm — it's just "closer than 0.7."

**Risk:** The reflex loop threshold (`distance_m < 0.3`) and safety gate
threshold (`distance_m < 0.4`) no longer mean real meters. They mean
"proximity score > 0.7" and "> 0.6" respectively. The relative ordering is
correct (high proximity = close = should stop), but the absolute values
are not calibrated.

**Mitigation:** The thresholds are conservative — if anything, the pseudo-
distance overestimates closeness (a proximity of 0.6 already triggers the
safety gate). We can tune the `OBSTACLE_THRESHOLD` and the `1.0 - score`
mapping once we test with real obstacles. When we add a real distance
sensor (ultrasonic, ToF, or stereo), we swap the conversion function and
the thresholds become real meters again.

### 3. No object labels for the brain

**Before:** Gemini got detections like `[{label: "chair", distance_m: 1.2}]`
and could reason "there's a chair ahead, go around it."
**After:** Gemini gets `[{label: "obstacle", distance_m: 0.3}]` — it knows
something is there but not what.

**Risk:** The brain loses object-level reasoning. "A person ahead" vs
"a chair ahead" matters for a rescue rover.

**Mitigation:** Gemini still gets the JPEG frame directly via `input_image=`
in the Backboard `send_message` call. It can see what the obstacle is from
the image — the detections just add spatial context ("close, center"). The
scene description from Gemini ("a person lying on the floor 2m ahead") is
richer than the detection label anyway. The depth proximity tells the brain
*where*; Gemini tells it *what*.

### 4. Wi-Fi dependency for depth

**Before:** OAK-D depth was on-device, no network needed.
**After:** Depth requires Wi-Fi to the laptop. If Wi-Fi drops, no depth.

**Risk:** The reflex loop loses obstacle avoidance if Wi-Fi dies. The brain
can still see (JPEG is captured locally) but can't detect obstacles for safety.

**Mitigation:** The `DEPTH_STALENESS_S = 2.0` check returns empty detections
when depth is stale. Empty detections = reflex loop doesn't override = brain
drives without safety. This is **not safe** for autonomous driving. Options:
- **Near-term:** Treat stale depth as "blocked ahead" (return a center
  detection at distance 0.0) so the reflex loop stops the robot when depth
  is unavailable. Conservative but safe.
- **Better:** Add an onboard fallback sensor (ultrasonic HC-SR04 is ~$5,
  works without Wi-Fi, gives real distance in meters).
- **Best:** Add stereo or ToF camera on the Pi for onboard depth, use the
  laptop depth as a secondary/upgrade path.

### 5. Frame rate mismatch

**Before:** Camera and depth both at 30 Hz, synchronized.
**After:** Camera at 15 Hz, depth at ~1-5 Hz (laptop inference limited).
The JPEG stored for Gemini may be from a different frame than the depth
result.

**Risk:** The brain sees a scene description from frame N and detections
from frame N-3. For a slow-moving rover this is fine (not much changes in
200ms-1s), but it's not perfectly synchronized.

**Mitigation:** The brain runs at ~1 Hz, so it only takes one frame per
episode. The depth result is from at most 1 second ago. For the demo this
is acceptable. The reflex loop runs faster but only needs to know "is
something close right now" — a 1-second-old depth result is still useful
for that.

---

## What "adding other stuff to measure distance" looks like

The bridge is designed so the conversion function (`_proximity_to_detections`)
is the only thing that needs to change when we get better distance data:

| Sensor | What it gives | How to integrate |
|--------|--------------|-----------------|
| Ultrasonic (HC-SR04) | Real distance in meters, single beam | Add as a separate detection at bearing 0° with real `distance_m` |
| ToF (VL53L0X) | Real distance in meters, single point | Same as ultrasonic, more precise |
| Stereo camera | Depth map + real distance | Replace the laptop depth path entirely, convert depth map to detections |
| OAK-D S2 (if obtained) | Depth + on-device YOLO | Replace `perception/camera.py` with the original OAK-D implementation |
| LiDAR (if obtained) | Precise distance + angle | Direct to Detection objects, skip conversion entirely |

The key insight: the `Detection` interface (`label, bbox, distance_m, bearing_deg`)
is the right abstraction. The conversion from sensor-specific data to Detection
is the only thing that changes. The brain, reflex loop, safety gate, and
controller all work with Detection objects and don't care where they came from.

---

## Files changed

| File | Change |
|------|--------|
| `perception/camera.py` | Rewritten: OAK-D/DepthAI stubs → TCP bridge to laptop depth |
| `.env.example` | Added `DEPTH_SERVER_HOST` and `DEPTH_SERVER_PORT` |
| `CLAUDE.md` section 8 | Update hardware description (CSI camera, not OAK-D) |
| `CLAUDE.md` section 13 | Remove already-resolved items, add camera bridge item |

## Files NOT changed (by design)

| File | Why |
|------|-----|
| `brain/loop.py` | Same interface — `get_latest_frame()` and `get_latest_detections()` |
| `control/reflex.py` | Same interface — reads `list[Detection]` |
| `brain/safety.py` | Same interface — reads `list[Detection]` |
| `perception/vision.py` | Same interface — gets JPEG from `get_latest_frame()` |
| `main.py` | Same interface — imports `get_latest_detections` |
