# Gemini — MLH Best Use of Gemini API

**Prize:** Google Swag Kits. 1 winner.
**Scope:** push the boundaries of what is possible with the Gemini API.

---

## How the rover uses Gemini

Gemini is the rover's **eyes and its planner**. Both roles are routed through Backboard as BYOK — our own Gemini API key is connected in the Backboard dashboard, so Backboard calls Gemini on our behalf rather than the rover calling the Gemini SDK directly.

> **Accepted risk (team decision, 2026-09-19):** routing Gemini through Backboard as BYOK may count for less in this track's judging than a direct SDK call, because the judges want to see the Gemini API used directly. We took this trade because it strengthens the Backboard track's "whole stack" story and because the BYOK path is the documented Backboard flow. See `PRIZE_TRACKS.md` for the full reasoning.

### 1. Vision / scene understanding

`perception/vision.py` calls `brain.describe(content=..., image_path=...)`, which in `brain/backboard_client.py:78` sends the camera frame into Backboard with:

```python
llm_provider="google"
model_name="gemini-2.5-flash"
```

Backboard forwards the image + prompt to Gemini and returns a 2–3 sentence scene description: notable objects, free space, hazards. That description becomes `state.scene_description` in the deliberative loop (`brain/loop.py:33`).

### 2. Planner model

The brain's planner is also Gemini. `brain/backboard_client.py:87`:

```python
brain = BackboardBrain(llm_provider="google", model_name="gemini-2.5-pro")
```

So the same Backboard thread routes to two different Gemini models:
- **Gemini 2.5 Flash** for fast scene description (vision step).
- **Gemini 2.5 Pro** for deliberative planning (the agent loop that calls motion verbs).

This is the "push the boundaries" story for the track: Gemini is doing both perception and planning for a physical robot, not just text generation.

### 3. Semantic spatial annotation

Gemini's scene descriptions are now geolocated onto the occupancy map. After each episode, `brain/loop.py:_update_map` calls `mapper.add_annotation(pose, state.scene_description, "gemini")`, placing the text at the rover's current position. The map accumulates a trail of Gemini's understanding of the environment — "person lying on ground" at position A, "rubble pile blocking path" at position B — giving the operator a semantic spatial view that combines what Gemini saw with where the rover was when it saw it.

The annotations are streamed to the frontend at 5 Hz via WebSocket (`control/map_server.py`) and rendered as text overlays on the occupancy grid (`frontend/src/components/MapView.tsx`).

### 4. The vision prompt

`perception/vision.py:10`:

```
Describe the scene in 2-3 sentences: notable objects, free space, and any
hazards. Be concrete about direction and distance.
```

The detections from the depth pipeline are passed alongside the image so Gemini can ground its description in the rover's own sensor data, not just the raw pixels.

---

## Integration points

| File | Role |
|---|---|
| `perception/vision.py` | Frame + detections → Backboard (Gemini BYOK) → scene description |
| `brain/backboard_client.py` | `describe()` routes to `gemini-2.5-flash`; planner routes to `gemini-2.5-pro` |
| `brain/loop.py` | Consumes `scene_description` as the brain's input; feeds it to mapper as annotation |
| `control/mapper.py` | `add_annotation()` geolocates Gemini descriptions onto the occupancy grid |
| `control/map_server.py` | Streams annotations to frontend via WebSocket at 5 Hz |
| `frontend/src/components/MapView.tsx` | Renders Gemini annotations as text overlays on the map |
| Backboard dashboard | Where the Gemini API key is connected (BYOK) — not in `.env` |

> Note: `GEMINI_API_KEY` is intentionally **not** in `.env` — it's connected in the Backboard dashboard's provider settings, not passed as a direct SDK key. See `.env.example:22`.

---

## Demo narrative

"The rover sees through Gemini. Every deliberative tick, the camera frame goes to Gemini 2.5 Flash for a scene description — what's ahead, where the free space is, what's a hazard. Then Gemini 2.5 Pro is the planner that decides what to do next: drive forward, turn, stop, speak. Both are routed through our Backboard brain with our own Gemini key connected as BYOK. And Gemini's descriptions aren't just text in a conversation — they're geolocated onto a live occupancy map, so the operator sees 'person lying on ground' pinned to the exact spot where the rover saw them. One Backboard thread orchestrating two Gemini models for perception and planning on a physical robot, with spatial annotation."

The strongest single-line pitch for this track: **Gemini is both the rover's eyes (Flash) and its prefrontal cortex (Pro)** — perception, planning, and spatial annotation, on a moving robot.
