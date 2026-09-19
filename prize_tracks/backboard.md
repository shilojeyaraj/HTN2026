# Backboard.io — Built on Backboard

**Prize:** guaranteed internship interviews, $400 per team, swag. 1 winner.
**Scope:** build anything on Backboard — text, image, voice, 17,000+ models, memory, RAG, embeddings, tool calling, web search, one API. Judged on ambition; the more of the stack you use, the better the odds.

---

## How the rover uses Backboard

Backboard is the **core brain** and **orchestration harness** of the rover. Every deliberative decision — where to drive, what to say, how to respond to a spoken command — runs through a Backboard thread. The brain calls its teammates (vision, safety, mapper) as tools, retrieves rescue protocols from a RAG knowledge base, and stores mission findings in structured memory. This is the "whole stack in one key" story the track rewards.

The rover is a hierarchical two-loop system: a fast onboard reflex loop keeps the robot safe at 30 Hz with no cloud, while a slower deliberative loop (~1 Hz) does the thinking on Backboard. Backboard owns the entire slow loop.

### 1. Agent loop with tool calling

`brain/backboard_client.py` wraps the Backboard SDK (`backboard-sdk` v1.5.19) into a persistent `BackboardBrain` that holds one thread + assistant across every episode. Each tick:

1. Sends the scene description, current goal, and any user command into the thread (`send_message` with `llm_provider`, `model_name`, `tools`, `memory`).
2. If Backboard returns `REQUIRES_ACTION`, the rover executes each tool call (a motion verb, sensor read, or teammate call), then feeds the **real execution result** back via `submit_tool_outputs_simple` — the Inner Monologue pattern. The brain reacts to `stopped_by_obstacle` within the same episode and tries a different verb.
3. The loop is capped at `MAX_TOOL_ROUNDS = 6` so a misbehaving chain can't run forever.

### 2. RAG — rescue protocol knowledge base + encounter history

`brain/backboard_client.py` uploads **two documents** to the Backboard assistant on first run via `upload_document_to_assistant`:

1. `knowledge/rescue_protocols.md` — operational protocols for thermal hazards, victim communication, audio distress recognition, structural hazards, search patterns, triage, and hazardous materials.
2. `knowledge/encounter_history.md` — 8 past rescue encounter records (ENC-2026-0140 through 0147) with status (RESCUED/LOCATED/NO CONTACT), locations, durations, and a pattern summary.

Backboard chunks and embeds both documents, and automatically retrieves relevant sections when the brain encounters a matching situation — "thermal hazard" retrieves the approach protocol, "Sector 7-A" retrieves the Riverside Apartments encounter, "warehouse" retrieves the Harbor Warehouse encounter.

The brain can also explicitly query the knowledge base with the `search_knowledge` tool, which calls `search_memories` on the assistant. This makes RAG retrieval visible in the demo — the brain actively calls "search_knowledge('sector 7-A')" and gets back the encounter history.

### 3. Structured mission memory — encounters + findings

Beyond `memory="Auto"` (conversation memory), the brain uses Backboard's structured memory API in two ways:

**Pre-loaded encounter history:** On first run, `_ensure_initialized` loads all 8 past encounters into Backboard memory via `add_memory` with structured metadata (`sector`, `status`, `encounter_id`). The brain can search these with `search_knowledge("sector 7-A")` to find past encounters in a specific area.

**Live mission findings:** The `log_finding` tool lets the brain record discoveries as they happen — `[survivor] person located at (2.3, 1.1), conscious and speaking`. The `search_knowledge` tool searches both the RAG knowledge base and all stored memories. This gives the rover persistent mission memory that survives across episodes — it remembers what it found, where, and in what condition.

**Pattern analysis:** The `analyze_patterns` tool calls `get_memory_insights` on the assistant, letting Backboard analyze patterns across all stored memories — rescue success rates by location type, duration trends, sector risk patterns. The brain can discover: "residential sectors had a 33% rescue rate, while public infrastructure had 75%."

### 4. Teammates as Backboard tools

The brain doesn't just call motion verbs — it calls its **teammate agents** as Backboard tools, making Backboard the true orchestration harness:

| Tool | Teammate called | What it does |
|---|---|---|
| `look_around()` | Vision agent (Gemini Flash) | Re-describes the current scene on demand |
| `check_map(radius_m)` | Mapper agent | Returns nearby obstacles, sounds, heat, hazards, annotations |
| `check_safety(action)` | Safety agent | Vets a proposed action before execution |
| `search_knowledge(query)` | RAG + memory | Retrieves rescue protocols, past encounters, and mission findings |
| `log_finding(type, desc)` | Memory | Stores a mission finding in persistent memory |
| `analyze_patterns()` | Memory insights | Analyzes rescue patterns across all stored mission memory |

This moves orchestration from Python into Backboard's agent loop — the Leader (Planner) decides when to perceive, when to check safety, when to query the map, and when to log findings. That's the harness pattern: Backboard isn't just one agent, it's the coordination layer all agents report to.

### 5. Vision (Gemini routed through Backboard as BYOK)

`perception/vision.py` calls `brain.describe(content=..., image_path=...)`, which sends the camera frame into Backboard with `llm_provider="google"`, `model_name="gemini-2.5-flash"`. Our own Gemini API key is connected in the Backboard dashboard (BYOK), so Backboard calls Gemini on our behalf. This keeps vision inside the Backboard stack rather than a separate SDK call.

Gemini's scene descriptions are also geolocated onto the occupancy map as annotations (`mapper.add_annotation`), so the brain's visual understanding is tied to spatial positions — "person lying on ground" appears at the rover's position when it was seen.

### 6. Planner model routing

The planner itself is also Gemini: `brain/backboard_client.py` instantiates `BackboardBrain(llm_provider="google", model_name="gemini-2.5-pro")`. So the same Backboard thread is doing both vision (flash) and planning (pro) by routing to different models — that's the "17,000+ models, one API" story.

### 7. Conversation memory + spatial memory

`brain/loop.py` calls `brain.run_tools(..., memory="Auto")`, so the Backboard thread retains mission context across episodes — the rover remembers what it already explored, what it said, and what the operator last asked.

On top of Backboard's conversation memory, the occupancy map (`control/mapper.py`) gives the brain **spatial memory**: a persistent 2D grid of where obstacles, sounds, heat, hazards, and annotations are. After every episode, `_update_map` feeds the latest sensor readings into the map, so the brain's spatial model grows over time. The map is streamed to the frontend at 5 Hz via WebSocket (`control/map_server.py`), giving the operator the same spatial view the brain is building.

### 8. Transcript-driven voice input

The laptop runs faster-whisper locally (`laptop/audio.py`) for always-on speech transcription. Final transcripts arrive via the Pi-to-laptop TCP pipeline, are buffered in `TranscriptBuffer` (`perception/transcript.py`), and consumed by the brain loop each episode as `state.last_user_command`. The brain then routes that text through the Baseten command parser (fast path) or the full Backboard reasoning loop. This means the Backboard thread receives voice commands without a push-to-talk button — always-on, local, no cloud STT round-trip.

---

## Backboard feature usage checklist

| Backboard feature | How we use it | File |
|---|---|---|
| **Agent loop** | `send_message` + `submit_tool_outputs_simple` (Inner Monologue) | `backboard_client.py` |
| **Tool calling** | 16 verbs (10 motion/sensor + 6 teammate/RAG/memory/insights) | `tools.py` |
| **Memory (Auto)** | Conversation memory across episodes | `loop.py` |
| **Memory (structured)** | `add_memory` for encounters + findings, `search_memories` for retrieval | `backboard_client.py` |
| **Memory insights** | `get_memory_insights` for pattern analysis across all stored memory | `backboard_client.py` |
| **RAG** | `upload_document_to_assistant` with 2 documents (rescue protocols + encounter history) | `backboard_client.py` |
| **Image input** | `input_image=` for camera frame → Gemini Flash | `backboard_client.py` |
| **Model routing (BYOK)** | Gemini Flash for vision, Gemini Pro for planning | `backboard_client.py` |
| **Assistant management** | `create_assistant` for persistent assistant with knowledge base | `backboard_client.py` |
| **Thread persistence** | One thread across all episodes | `backboard_client.py` |

**10 Backboard features used.** Not yet using: embeddings (`list_embedding_models`), web search, voice, video, realtime audio.

---

## Integration points

| File | Role |
|---|---|
| `brain/backboard_client.py` | SDK wrapper, persistent thread, tool-calling loop, vision describe, RAG upload, memory search/log |
| `brain/loop.py` | Deliberative episode: perceive → (parser fast-path) → Backboard brain → safety gate → execute → update map |
| `brain/tools.py` | 16-verb tool schema + system prompt (motion, sensor, teammate, RAG, memory, insights) |
| `knowledge/rescue_protocols.md` | RAG knowledge base: thermal, victim comms, audio distress, structural, search, triage, hazmat protocols |
| `knowledge/encounter_history.md` | RAG + memory: 8 past rescue encounters with status, location, duration, and pattern summary |
| `perception/vision.py` | Frame → Backboard (Gemini BYOK) → scene description |
| `perception/transcript.py` | TranscriptBuffer: bridges local STT to brain's last_user_command |
| `control/mapper.py` | Spatial memory: occupancy grid with 6 sensor overlay layers + `nearby_summary` for `check_map` tool |
| `control/map_server.py` | WebSocket streaming map to frontend at 5 Hz |
| `control/pose.py` | Dead-reckoning pose estimator for map building |
| `.env` | `BACKBOARD_API_KEY` |

---

## Demo narrative

"The rover's brain is a Backboard agent — but it's not just one prompt. It's a harness. The brain calls 16 tools: motion verbs to drive, sensor reads to perceive, and teammate calls to coordinate with other agents. It calls `look_around` to ask the vision agent for a fresh scene description. It calls `check_map` to query the occupancy map for nearby obstacles and hazards. It calls `check_safety` to vet a risky move before executing. It calls `search_knowledge` to retrieve rescue protocols from a RAG knowledge base we uploaded to the assistant — thermal hazard approach, victim communication, structural collapse indicators — plus 8 past rescue encounters loaded into structured memory. It calls `log_finding` to store discoveries in Backboard's structured memory — every survivor found, every hazard identified, persisted across episodes. It calls `analyze_patterns` to learn from past encounters — Backboard analyzes rescue success rates, location patterns, and duration trends across all stored memory. One API, one thread, the whole cognitive stack — perception, planning, tool calling, RAG, structured memory, memory insights, conversation memory, spatial memory, and voice. Ten Backboard features in one rover."

The strongest single-line pitch for this track: **the rover's entire deliberative mind is one Backboard thread** — 16 tools, 2 RAG documents, 8 pre-loaded encounters, structured mission memory, pattern analysis, conversation memory, vision, planning, and spatial awareness, all orchestrated through one API.
