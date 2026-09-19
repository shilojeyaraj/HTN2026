# Backboard.io — Built on Backboard

**Prize:** guaranteed internship interviews, $400 per team, swag. 1 winner.
**Scope:** build anything on Backboard — text, image, voice, 17,000+ models, memory, RAG, embeddings, tool calling, web search, one API. Judged on ambition; the more of the stack you use, the better the odds.

---

## How the rover uses Backboard

Backboard is the **core brain** of the rover. Every deliberative decision — where to drive, what to say, how to respond to a spoken command — runs through a Backboard thread. This is the "whole stack in one key" story the track rewards.

The rover is a hierarchical two-loop system: a fast onboard reflex loop keeps the robot safe at 30 Hz with no cloud, while a slower deliberative loop (~1 Hz) does the thinking on Backboard. Backboard owns the entire slow loop.

### 1. Agent loop with tool calling

`brain/backboard_client.py` wraps the Backboard SDK (`backboard-sdk` v1.5.19) into a persistent `BackboardBrain` that holds one thread + assistant across every episode. Each tick:

1. Sends the scene description, current goal, and any user command into the thread (`send_message` with `llm_provider`, `model_name`, `tools`, `memory`).
2. If Backboard returns `REQUIRES_ACTION`, the rover executes each tool call (a motion verb or sensor read), then feeds the **real execution result** back via `submit_tool_outputs_simple` — the Inner Monologue pattern. The brain reacts to `stopped_by_obstacle` within the same episode and tries a different verb.
3. The loop is capped at `MAX_TOOL_ROUNDS = 6` so a misbehaving chain can't run forever.

### 2. Memory — mission context + spatial memory

`brain/loop.py` calls `brain.run_tools(..., memory="Auto")`, so the Backboard thread retains mission context across episodes — the rover remembers what it already explored, what it said, and what the operator last asked.

On top of Backboard's conversation memory, the occupancy map (`control/mapper.py`) gives the brain **spatial memory**: a persistent 2D grid of where obstacles, sounds, heat, hazards, and annotations are. After every episode, `_update_map` feeds the latest sensor readings into the map, so the brain's spatial model grows over time. The map is streamed to the frontend at 5 Hz via WebSocket (`control/map_server.py`), giving the operator the same spatial view the brain is building.

### 3. Vision (Gemini routed through Backboard as BYOK)

`perception/vision.py` calls `brain.describe(content=..., image_path=...)`, which sends the camera frame into Backboard with `llm_provider="google"`, `model_name="gemini-2.5-flash"`. Our own Gemini API key is connected in the Backboard dashboard (BYOK), so Backboard calls Gemini on our behalf. This keeps vision inside the Backboard stack rather than a separate SDK call.

Gemini's scene descriptions are also geolocated onto the occupancy map as annotations (`mapper.add_annotation`), so the brain's visual understanding is tied to spatial positions — "person lying on ground" appears at the rover's position when it was seen.

### 4. Planner model routing

The planner itself is also Gemini: `brain/backboard_client.py:87` instantiates `BackboardBrain(llm_provider="google", model_name="gemini-2.5-pro")`. So the same Backboard thread is doing both vision (flash) and planning (pro) by routing to different models — that's the "17,000+ models, one API" story.

### 5. Tool schema

`brain/tools.py` defines 10 verbs the brain can call: `forward`, `backward`, `turn`, `stop`, `speak`, `get_obstacles`, `get_state`, `get_temperature`, `get_audio`, `get_gyro`. The system prompt (`tools.py:92`) frames the rover as a rescue responder that narrates what it finds, polls environmental sensors when the situation calls for it, and treats spoken commands as a person talking to it. The schema is small and stable so the prompt prefix stays cacheable.

### 6. Transcript-driven voice input

The laptop runs faster-whisper locally (`laptop/audio.py`) for always-on speech transcription. Final transcripts arrive via the Pi-to-laptop TCP pipeline, are buffered in `TranscriptBuffer` (`perception/transcript.py`), and consumed by the brain loop each episode as `state.last_user_command`. The brain then routes that text through the Baseten command parser (fast path) or the full Backboard reasoning loop. This means the Backboard thread receives voice commands without a push-to-talk button — always-on, local, no cloud STT round-trip.

---

## Integration points

| File | Role |
|---|---|
| `brain/backboard_client.py` | SDK wrapper, persistent thread, tool-calling loop, vision describe |
| `brain/loop.py` | Deliberative episode: perceive → (parser fast-path) → Backboard brain → safety gate → execute → update map |
| `brain/tools.py` | 10-verb tool schema + system prompt |
| `perception/vision.py` | Frame → Backboard (Gemini BYOK) → scene description |
| `perception/transcript.py` | TranscriptBuffer: bridges local STT to brain's last_user_command |
| `control/mapper.py` | Spatial memory: occupancy grid with 6 sensor overlay layers |
| `control/map_server.py` | WebSocket streaming map to frontend at 5 Hz |
| `control/pose.py` | Dead-reckoning pose estimator for map building |
| `.env` | `BACKBOARD_API_KEY` |

---

## Demo narrative

"The rover's brain is a Backboard agent. It sees the scene through a Gemini model we connected in the Backboard dashboard, reasons about what to do next with Gemini 2.5 Pro as the planner, calls motion tools to drive, gets the real result of each action fed back into the same thread, and remembers the mission across turns with Backboard memory. On top of conversation memory, it builds a spatial memory — a live occupancy map that grows as it drives, fusing six sensor types into one grid. Voice commands arrive always-on from a local whisper model, no button needed. One API, one thread, the whole cognitive stack — perception, planning, memory, spatial awareness, and voice."

The strongest single-line pitch for this track: **the rover's entire deliberative mind is one Backboard thread** — vision, planning, tool calling, conversation memory, and spatial memory all live there.
