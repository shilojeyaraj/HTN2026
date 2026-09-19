# PRIZE_TRACKS.md

Sponsor prize tracks for the Hack the North 2026 rover, with each track's scope and how our project targets it. Companion to CLAUDE.md and BACKBOARD.md. Prize selections must be submitted on Devpost by **2:00 PM EDT Saturday**, so one person owns that.

Judging is a **live demo** (not slides), scored on WOW factor, technical ability, originality, and design. The robot must physically move.

---

## Committed tracks (build toward these five)

**2026-09-19 team decision, overriding the "overlap trap" reasoning below for Gemini and
ElevenLabs:** route them through Backboard (BYOK — our own Gemini/ElevenLabs API keys,
connected in the Backboard dashboard, so Backboard calls them on our behalf) rather than
calling their SDKs directly, accepting the risk that this is a weaker claim for their
specific tracks than a direct call. Baseten stays a separate, direct slice (STT) since
Backboard doesn't document Baseten as a voice provider. The original reasoning is kept
below for context on what's being traded away.

The overlap trap: Gemini, ElevenLabs, and Baseten only count if we use them **directly and visibly**. If they are just models Backboard routes to under the hood, the claim is weak and possibly disqualifying, because those judges want to see their own API in the project. So each sponsor gets a **distinct, separately-demoable slice** that does not overlap. That means routing some pieces around Backboard on purpose.

### Backboard.io: Built on Backboard
- **Prize:** guaranteed internship interviews, $400 per team, swag. 1 winner.
- **Scope:** build anything, the only rule is it runs on Backboard. Text, image, voice, 17,000+ models, memory, RAG, embeddings, tool calling, web search, one API. Judged on ambition; the more of the stack you use, the better the odds.
- **Our role for it:** the brain core. Agent loop, tool calling, thread state, planner model routing, and (recommended) memory. This is where the "whole stack in one key" story lives.

### Rox: Best AI Agent
- **Prize:** $10K first, $2K second. 2 winners. (Biggest cash on the board.)
- **Scope:** an LLM-driven agent operating on real-world messy data (unstructured, incomplete, conflicting, noisy) that takes meaningful actions. Rewards data cleaning/validation, multi-source resolution, error handling, decision-making under uncertainty. Judged on technical complexity, creativity, handling messiness, practical utility.
- **Our role for it:** pitch framing, no extra code. A rover acting on noisy, incomplete sensor data under uncertainty is exactly the ask.

### Gemini: MLH Best Use of Gemini API
- **Prize:** Google Swag Kits. 1 winner.
- **Scope:** push the boundaries of what is possible with the Gemini API.
- **Our role for it (revised):** vision / scene understanding, **routed through Backboard** (`llm_provider="google"`), using our own Gemini API key connected in the Backboard dashboard. Accepted risk: this may count for less than a direct SDK call in judging.

### ElevenLabs: MLH Best Use of ElevenLabs
- **Prize:** wireless earbuds. 1 winner.
- **Scope:** natural, human-sounding, emotionally expressive voice.
- **Our role for it (revised):** voice out, **routed through Backboard** (`voice={"tts": {"provider": "elevenlabs", ...}}`), using our own ElevenLabs API key connected in the Backboard dashboard. Same accepted risk as Gemini above.

### Baseten: Best Use of Baseten
- **Prize (per member):** Grand: SF trip + final-round interviews + $200 credits + signed *Inference Engineering*. Runner-up: AirPods 4 + $100 credits + book. 2 winners.
- **Scope:** creative, meaningful use of Baseten (inference or training).
- **Our role for it:** voice in, a speech-to-text model (Whisper Large V3 Turbo) hosted on Baseten, called **directly** (not through Backboard — undocumented as a Backboard voice provider). Optional bigger swing, deferred: fine-tune a small command-parser model on their H100 workstations (visit the booth to enable) once the core robot works — a side quest, not the track-qualifying deliverable.

**Cost of this division:** Gemini and ElevenLabs now go through Backboard (BYOK), which strengthens the Backboard track's "how much of the stack" story but weakens the direct-use claim for those two sponsors specifically. Baseten stays a separate direct slice for voice-in. Backboard owns orchestration, planner routing, tools, memory, vision, and voice-out.

---

## Stacks cleanly (add if the base build is solid)

### Huawei: openJiuwen Multi-Agent Challenge
- **Prize (per member):** 1st Huawei Watch GT 6 + internship opportunity at Huawei Toronto Research Center (subject to interview); 2nd FreeClip 2 Earbuds + office tour. Up to $40 team API credits. 2 winners.
- **Scope:** a functional multi-agent app solving a real problem through genuine collaboration (task decomposition, communication, tool use, coordination), not chained prompts. Building on JiuwenSwarm/WorkSwarm is encouraged, not required.
- **Our role for it:** per-role model routing on Backboard (scene, planner, safety as coordinating agents) is a real heterogeneous multi-agent system. Highest-value Huawei prize and it fits the architecture.

### Bracket Bot: Best Use of Bracket Bot Hardware
- **Prize:** 1st 4x Bambu A1 Mini + 4x SO-101 kits; 2nd 4x SO-101 kits; 3rd 4x SO-101 robots. 3 winners.
- **Scope:** use Bracket Bot to interact with the physical world (navigation, voice, manipulation, teleoperation). Robot must be essential to the idea.
- **Our role for it:** only if we build on their robot base instead of a scratch rover. Independent of the brain stack, so it stacks freely. De-risks the mechanical build.

### MLH: Best Use of Tiger Data
- **Prize:** Stream Deck Mini. 1 winner.
- **Scope:** PostgreSQL extended for real-time data, time-series, dashboards (IoT monitoring, analytics).
- **Our role for it:** a rover is a sensor-stream firehose. Log telemetry, live dashboard. Cheap add-on, independent of the brain.

---

## Ruled out (conflict with a cloud Backboard brain)

### Huawei: OMNI Live Challenge
- **Prize (per member):** Watch GT 6 / FreeClip 2 + office tour. 2 winners.
- **Scope:** real-time multimodal edge app using Huawei's OMNI model as the core, incorporating vision, speech, and language end-to-end.
- **Why not:** requires OMNI as the multimodal core, which competes with Backboard for the same slot. Pivoting here means tearing out routing, voice, memory, and tools and rebuilding around one required model. Weaker prize than the Backboard + openJiuwen path.

### QNX: Embedded System with QNX that Uses AI
- **Scope:** QNX OS + an open-source AI module, running on embedded hardware or the QNX VM, **not the cloud**.
- **Why not:** the no-cloud requirement rules out a cloud brain entirely.

---

## Separate projects (fit our background, not this robot)

### Dryft Company Challenge
- **Prize:** $2000. Make an autoregressive transformer generate tokens as fast as possible (Triton kernels, op fusion, memory layouts). Runs on H100s, correctness-tested, benchmarked on hidden workloads. Standalone, only if a teammate can carry the rover.

### Dominion Dynamics: WHITEOUT
- **Prize:** $2000 / $1000 / $500 + guaranteed first-round interview. 3 winners. Live Arctic sim coordinating a fleet (aircraft, quadcopters, rovers, sensor towers) over MAVLink to track a target. Multi-agent autonomy, but a separate scored challenge, not this build.

---

## Build order (let the bottom fall off if time runs short)

Each layer is an additive bonus track on a robot that already works, not a dependency that can sink the demo.

1. **Robot drives with the onboard reflex loop.** Safety floor, no cloud.
2. **Backboard brain.** Qualifies Backboard and Rox on its own.
3. **Gemini vision** (direct). Adds the Gemini track.
4. **ElevenLabs voice out** (direct). Adds the ElevenLabs track.
5. **Baseten STT** (direct). Adds the Baseten track.
6. **openJiuwen framing** (multi-agent routing) and any add-ons (Bracket Bot base, Tiger Data dashboard).

Realistic focused stack on one robot: **Backboard + Rox + Gemini + ElevenLabs + Baseten**, with **openJiuwen** as the clean Huawei co-pitch and Bracket Bot / Tiger Data as low-cost extras.

---

## Admin

- Submit prize selections on Devpost by **2:00 PM EDT Saturday**. Assign an owner.
- Confirm eligibility on any track where it matters (for example, sponsor-employee/intern rules).
