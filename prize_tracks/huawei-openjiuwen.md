# Huawei — openJiuwen Multi-Agent Challenge

**Prize (per member):** 1st Huawei Watch GT 6 + internship opportunity at Huawei Toronto Research Center (subject to interview); 2nd FreeClip 2 Earbuds + office tour. Up to $40 team API credits. 2 winners.
**Scope:** a functional multi-agent app solving a real problem through genuine collaboration (task decomposition, communication, tool use, coordination), not chained prompts. Building on JiuwenSwarm/WorkSwarm is encouraged, not required.

> **Status:** stacks cleanly on top of the base build. No extra code required to qualify — the architecture already is a heterogeneous multi-agent system. This is the highest-value Huawei prize and it fits the existing design.

---

## JiuwenSwarm fit analysis

We read through the [JiuwenSwarm documentation](https://github.com/openJiuwen-ai/jiuwenswarm) to verify our system matches the pattern the track rewards.

### JiuwenSwarm's core collaboration pattern

```
User states goal → Leader analyzes → Leader forms team → Leader breaks down tasks
→ Teammates claim tasks → Teammates execute → Teammates report back
→ Leader consolidates → Final deliverable
```

Their docs call this **Coordination Engineering** — "not the strongest agent, but better coordination." That's exactly our architecture.

### Mapping our agents to JiuwenSwarm's Leader/Teammate model

| JiuwenSwarm concept | Our system | How it maps |
|---|---|---|
| **Leader** (decomposes tasks, forms team, assigns work) | **Planner Agent** (Gemini Pro via Backboard) | Receives the rescue goal + scene + user command, decomposes into tool calls, coordinates specialized agents, consolidates results via Inner Monologue |
| **Teammate** (specialized, claims tasks, executes, reports back) | **8 specialized agents** (see table below) | Each handles one role, reports results back to the Planner through shared state or direct tool returns |
| **Distributed Swarm** (agents across processes/machines) | Pi + laptop + cloud | Agents run on 3 machines: Pi (reflex, pose, mapper, controller), laptop (STT, depth), cloud (Backboard/Gemini, Baseten, ElevenLabs) |
| **Task Planning** (dynamic breakdown, interrupt/resume) | Brain episode loop | Each episode: perceive → check transcripts → parse fast-path → plan → safety gate → execute → update map. Voice commands interrupt the idle wait between episodes. |
| **Tool Permissions & Security** (tools require approval) | Safety Agent (SayCan veto) + Arbiter (priority mux) | The Safety Agent approves/vetoes each action. The Arbiter enforces priority: reflex > brain > watchdog. Tools can't execute without passing the safety gate. |
| **Skills** (installable capability packages) | 10 verb tool schema | Our verbs are the capability set — forward, backward, turn, stop, speak, get_obstacles, get_state, get_temperature, get_audio, get_gyro. Not installable/removable like JiuwenSwarm Skills, but the same concept of a fixed, well-named primitive API. |

### Track requirements checklist

| Track requirement | Our system | Evidence |
|---|---|---|
| **Task decomposition** | Rescue mission decomposed into 9 distinct roles | See agent table below |
| **Communication** | RobotState (shared dataclass), TranscriptBuffer, Backboard thread, Inner Monologue, Mapper | 5 communication channels between agents |
| **Tool use** | 10 verbs the Planner calls; Parser outputs structured tool calls | `brain/tools.py` |
| **Coordination** | Safety vetoes Planner, Reflex overrides at Arbiter, Parser shortcuts Planner, Mapper feeds spatial context back | 4 coordination mechanisms with conflict resolution |
| **Not chained prompts** | 4 different LLMs + 3 classical subsystems — heterogeneous, each chosen for its role | Not one model doing everything |
| **Distributed** | Agents across Pi, laptop, and cloud | 3 machines, 2 networks |
| **Real problem** | Autonomous rescue rover searching for survivors | Physical robot, live demo |
| **Building on JiuwenSwarm** | Not required — track says "encouraged, not required" | We use Backboard for orchestration, which is the same coordination pattern |

---

## The multi-agent split

### Leader

| Agent | Model / System | Location | What it does |
|---|---|---|---|
| **Planner** (Leader) | Gemini 2.5 Pro (Backboard BYOK) | Cloud | Reasons over scene + goal + command, decomposes into tool calls, coordinates teammates, consolidates results via Inner Monologue, retains mission context with Backboard memory |

### Teammates

| Agent | Model / System | Location | What it does | Reports back to |
|---|---|---|---|---|
| **Vision** | Gemini 2.5 Flash (Backboard BYOK) | Cloud | Describes camera frame: objects, free space, hazards | Planner (via `state.scene_description`) |
| **STT** | faster-whisper `base.en` (CTranslate2 INT8) | Laptop CPU | Always-on speech transcription, provisional + final transcripts | Planner (via TranscriptBuffer → `state.last_user_command`) |
| **Parser** (fast path) | Qwen3-1.7B LoRA (Baseten H100, vLLM) | Cloud | Parses simple voice commands into verb calls, shortcuts the Planner | Direct execution (bypasses Planner) |
| **Safety** | Classical (no LLM) | Pi | SayCan veto gate — refuses unsafe actions | Planner (returns OK or VETO) |
| **Reflex** | Classical (no LLM, no cloud) | Pi (30 Hz) | Emergency stop, obstacle avoidance, final authority over motors | Arbiter (overrides Planner) |
| **Mapper** | Classical (numpy) | Pi | Fuses 6 sensor types into 2D occupancy grid with log-odds confidence | Frontend (WebSocket at 5 Hz) + Planner (via `get_obstacles`) |
| **Pose** | Classical (complementary filter) | Pi (30 Hz) | Dead-reckoning from gyro + velocity | Mapper + Planner (via `get_state`) |
| **TTS** | ElevenLabs `eleven_flash_v2_5` | Cloud | Voice output — speaks to victims and operator | Speaker (async, daemon thread) |

### Communication channels between agents

| Channel | From → To | Mechanism |
|---|---|---|
| RobotState | All agents | Shared dataclass (`brain/state.py`) — `scene_description`, `detections`, `last_user_command`, `safety_status`, `robot_pose` |
| TranscriptBuffer | STT → Planner | Thread-safe queue (`perception/transcript.py`) — `consume_final()` returns latest transcript |
| Backboard thread | Vision ↔ Planner | Same thread, different model routing — Vision output becomes Planner input |
| Inner Monologue | Controller → Planner | `submit_tool_outputs_simple` — real execution results fed back (`completed`, `stopped_by_obstacle`) |
| Arbiter | Reflex + Planner → Motors | Priority mux — reflex (high) overrides planner (low); watchdog halts if both stale 0.5s |
| Mapper | All sensors → Planner + Frontend | Occupancy grid + overlay layers → WebSocket at 5 Hz; Planner reads via `get_obstacles` |
| TCP pipeline | Pi ↔ Laptop | Interleaved MJPEG + PCM audio over single TCP connection |

### Coordination mechanisms (conflict resolution)

1. **Safety veto** — Safety Agent can block Planner's `forward` call → returns `{"status": "vetoed"}`
2. **Reflex override** — Reflex Agent (30 Hz) overrides Planner at the Arbiter → motors stop
3. **Parser shortcut** — Parser Agent can skip the Planner entirely for simple commands → direct execution
4. **Watchdog halt** — if both Reflex and Planner go stale for 0.5s → motors halt (fail-safe)
5. **Spatial feedback** — Mapper shows Planner which areas are explored/occupied via `get_obstacles`

---

## Why this is a real multi-agent system, not chained prompts

- **Different models for different roles.** A chained-prompt system uses one model for everything. The rover uses Gemini Flash for vision, Gemini Pro for planning, a fine-tuned Qwen3 for parsing, local faster-whisper for STT, ElevenLabs for TTS, and classical algorithms for safety, mapping, and pose. That's heterogeneous — each agent is chosen for its role.
- **Coordination through shared state.** The STT agent's output (transcript text) becomes the parser agent's input. The vision agent's output (`scene_description`) becomes the planner agent's input. The planner's proposed action becomes the safety agent's input. The safety agent's veto becomes feedback to the planner. All sensor agents' outputs flow into the mapper, which builds the spatial model. That's agent-to-agent communication, not a linear chain.
- **Tool use.** The planner agent calls 10 tools (motion verbs + sensor reads). The parser agent outputs a structured tool call. The mapper agent provides spatial context back to the planner through `get_obstacles` and `get_state`. That's the "tool use" the scope asks for.
- **Decision-making under uncertainty.** The safety agent can override the planner. The parser agent can shortcut the planner. The reflex agent can override both. That's coordination with conflict resolution, not a single thread of reasoning.
- **Spatial coordination.** The mapper agent fuses outputs from all sensor agents into a shared spatial model that the planner and operator both use. This is a level of coordination beyond text-based agent communication — the agents are coordinating through a shared map of the physical world.
- **Distributed deployment.** Agents run on 3 machines (Pi, laptop, cloud) connected over Wi-Fi. The JiuwenSwarm docs call this "Distributed Agent Swarm — Leader and Teammates deploy across processes and machines, coordinating at scale." Our system does this natively.

### What we are NOT doing (and why that's OK)

We are not building on JiuwenSwarm/WorkSwarm — the track says it's "encouraged, not required." Our multi-agent system uses Backboard for orchestration with per-role model routing plus classical subsystems, which is the same coordination pattern JiuwenSwarm automates.

| JiuwenSwarm feature | Our approach | Why it's fine |
|---|---|---|
| Dynamic team formation (Leader assembles team per task) | Static team — agents always active | Rescue missions need all agents always on; dynamic formation adds latency |
| Skill Self-Evolution (auto-optimizes on errors) | Not implemented | Not required by track scope |
| Swarmflow (deterministic Python workflows) | Dynamic agent loop with Inner Monologue | Both are valid coordination patterns; ours adapts in real-time |
| Skills (installable capability packages) | 10 fixed verbs | Same concept (well-named primitive API), not installable |
| Task Planning with todo tools | Brain reasons over scene + goal | Could add structured todos, but the agent loop already decomposes dynamically |

If asked at the booth: "our multi-agent coordination is the Backboard planner acting as Leader, routing to distinct models per role — Gemini Flash for vision, Gemini Pro for planning, Qwen3 for parsing, faster-whisper for STT, ElevenLabs for TTS — with classical agents handling safety, mapping, and pose. That's the same Leader/Teammate decomposition JiuwenSwarm automates, implemented with Backboard as the orchestration layer."

---

## Integration points

| File | Role |
|---|---|
| `brain/backboard_client.py` | Leader: one thread, two Gemini models routed by role (Flash for vision, Pro for planning) |
| `brain/loop.py` | Orchestrates the agents: perceive → parser fast-path → planner → safety → execute → update map |
| `brain/tools.py` | 10-verb tool schema + system prompt (the Leader's tool set) |
| `perception/vision.py` | Vision teammate: frame → Gemini Flash → scene description |
| `brain/command_parser.py` | Parser teammate: voice command → Qwen3 fine-tune → verb call |
| `brain/safety.py` | Safety teammate: SayCan veto gate |
| `brain/state.py` | Shared state (`RobotState`) — the communication channel between agents |
| `control/reflex.py` | Reflex teammate: 30 Hz classical safety loop, can override the Leader |
| `control/arbiter.py` | Priority mux: reflex > brain > watchdog halt |
| `control/mapper.py` | Mapper teammate: fuses 6 sensor types into occupancy grid with log-odds confidence |
| `control/pose.py` | Pose teammate: dead-reckoning from gyro + velocity |
| `perception/transcript.py` | TranscriptBuffer: communication channel between STT teammate and Leader |
| `laptop/audio.py` | STT teammate: local faster-whisper, provisional + final transcripts |
| `voice/tts.py` | TTS teammate: ElevenLabs direct SDK call, async playback |
| `control/map_server.py` | Streams the shared spatial model to the frontend at 5 Hz |

---

## Demo narrative

"The rover's brain isn't one prompt — it's a team of 9 agents. A Leader agent (Gemini Pro on Backboard) receives the rescue mission and decomposes it: it calls a vision teammate (Gemini Flash) to perceive the scene, a parser teammate (a Qwen3 we fine-tuned on Baseten) to shortcut voice commands, a safety teammate (classical, 30 Hz) to veto unsafe actions, a mapper teammate to fuse all six sensor types into a live occupancy map, a pose teammate to track position by dead-reckoning, an STT teammate (local faster-whisper) to always-on transcribe speech, and a TTS teammate (ElevenLabs) to speak back to victims. They coordinate through shared state, a transcript buffer, and a Backboard thread — the STT teammate's output is the parser's input, the vision teammate's output is the Leader's input, all sensor outputs flow into the mapper's spatial model, and the safety teammate can veto the Leader at any time. It's distributed across three machines — Pi, laptop, and cloud. That's genuine multi-agent collaboration: task decomposition, communication, tool use, spatial coordination, conflict resolution, and distributed deployment."

The strongest single-line pitch for this track: **the rover is a heterogeneous multi-agent system — 1 Leader + 8 Teammates across 4 LLMs and 3 classical subsystems, distributed across 3 machines, coordinating through shared state, a transcript buffer, a priority arbiter, and a live spatial map**.
