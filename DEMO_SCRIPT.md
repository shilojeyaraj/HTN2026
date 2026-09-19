# Live Demo Script

Hack the North 2026 — Rescue Rover
Judging: WOW factor, technical ability, originality, design
Time: 3-5 minutes per team

---

## Pre-Demo Setup (15 minutes before judging)

### Terminal 1 — Laptop depth + STT server
```bash
cd ~/VScode/htn2026/HTN2026
source .venv/bin/activate
python -m laptop.server --host 0.0.0.0 --port 8765
```

### Terminal 2 — Frontend dashboard
```bash
cd ~/VScode/htn2026/HTN2026/frontend
npm run dev
```
Open browser to the Vite URL. Dashboard shows: camera feed, live map, transcript, encounter panel.

### Terminal 3 — Rover brain (on Pi or dev machine)
```bash
cd ~/VScode/htn2026/HTN2026
source .venv/bin/activate
python main.py
```

### Fallback: simulated demo (no hardware needed)
```bash
# Terminal 3 replacement — simulates the full rescue scenario
python control/demo_map.py
```

### Verify before judges arrive
- [ ] Frontend dashboard loads with map visible
- [ ] Map shows rover icon with sensor cone
- [ ] Camera feed shows live video (or blank if no camera)
- [ ] `.env` has all API keys: BACKBOARD_API_KEY, BASETEN_API_KEY, BASETEN_PARSER_MODEL_ID, ELEVENLABS_API_KEY, VOICE_ID
- [ ] Speaker is connected and ElevenLabs TTS works (test: `python -c "from voice.tts import speak; speak('Rescue rover online')"`)
- [ ] Microphone picks up speech (laptop server shows transcript events in terminal)

---

## Demo Flow (3-5 minutes)

### 0:00 — Setup Hook (15 seconds)

**You say:** "This is an autonomous rescue rover. It searches hazardous areas for survivors, maps what it finds, and talks to people it discovers. The brain isn't one prompt — it's a team of 9 AI agents running across three machines."

**Judges see:** Frontend dashboard with the live map, camera feed, and transcript panel.

### 0:15 — Launch the Mission (30 seconds)

**You say:** "Rover, begin search and rescue operations."

**What happens:**
- STT transcribes the command (faster-whisper on laptop, ~200ms)
- Transcript appears in the transcript panel
- Baseten command parser tries the fast path — "begin search" isn't a simple verb, falls through
- Backboard brain (Gemini Pro) receives the command, reasons about what to do
- Brain calls `forward(0.5)` to start exploring

**You say:** "The rover heard me through the local whisper model — no button, no cloud round-trip for speech. The command went to a Backboard agent running Gemini Pro, which decided to start driving forward."

**Prize callout:** [Backboard — agent loop + tool calling] [Baseten — local STT + command parser] [ElevenLabs — if the rover speaks]

### 0:45 — The Rover Explores (60 seconds)

**What happens:**
- Rover drives forward, the map builds up in real-time
- Ultrasonic sensors ray-cast obstacles onto the occupancy grid (amber/cyan cells)
- Camera depth adds lower-confidence obstacles
- Trail appears behind the rover (green gradient line)
- Sensor cone sweeps ahead (semi-transparent cyan)

**You say:** "Watch the map build in real-time. Six sensor types fuse into one occupancy grid — ultrasonic, camera depth, audio, heat, hazards, and Gemini's scene descriptions. The rover knows where it's been and what's around it."

**You say:** "The brain is calling tools as it goes — `get_obstacles` to check what's ahead, `check_map` to see what's nearby, `look_around` to get a fresh scene description from Gemini Flash. All of these are Backboard tool calls, fed back through Inner Monologue so the brain reacts to what it finds."

**Prize callout:** [Rox — messy data fusion, occupancy grid, dead-reckoning] [Backboard — teammate tools, Inner Monologue] [Gemini — scene understanding via BYOK]

### 1:45 — Hazard Encounter (60 seconds)

**What happens:**
- Rover detects high heat (temperature sensor reads 72°C)
- A red heat dome appears on the map at the rover's position
- Brain calls `search_knowledge("thermal hazard approach")`
- Backboard retrieves the thermal hazard protocol from the RAG knowledge base
- Brain calls `speak("I detect high heat in this area. I'm going to find a safer path.")` — ElevenLabs speaks
- Brain calls `turn(90)` to route around the hazard
- Brain calls `log_finding("hazard", "overheat at 72C, rerouting")` — stored in Backboard memory

**You say:** "The rover just hit a thermal hazard. It called `search_knowledge` — that's a RAG retrieval from a knowledge base of real rescue protocols we uploaded to Backboard. It got back the thermal approach protocol: stop, announce the temperature, find an alternate route. Then it spoke to the operator through ElevenLabs, logged the finding to persistent memory, and turned away."

**Prize callout:** [Backboard — RAG, structured memory, memory insights] [ElevenLabs — voice output] [Gemini — if scene description identifies the heat source]

### 2:45 — Victim Discovery (60 seconds)

**What happens:**
- Rover detects a distress sound (microphone picks up "help!")
- Red danger soundwaves appear on the map — directional arcs centered on rover heading
- Sound marker placed on the map with the label "DISTRESS CALL"
- Brain calls `search_knowledge("victim communication")`
- Backboard retrieves the victim communication protocol
- Brain calls `speak("I hear you. I'm a rescue rover. Help is on the way. Can you tell me your name and if you're injured?")`
- Transcript panel shows the exchange
- Brain calls `log_finding("survivor", "distress call detected, voice contact established")`
- Brain calls `analyze_patterns()` — Backboard analyzes past encounter patterns

**You say:** "The microphone picked up a distress call. See the directional soundwaves on the map — that's the rover hearing danger in a specific direction. The brain searched its knowledge base for victim communication protocols, then spoke to the survivor through ElevenLabs. It also called `analyze_patterns` — Backboard analyzed 8 past rescue encounters and found that public infrastructure had a 75% rescue rate. The rover is learning from history."

**Prize callout:** [Backboard — RAG, memory insights, encounter history] [ElevenLabs — victim communication] [Huawei — multi-agent coordination: STT → brain → TTS → memory, all as Backboard tools]

### 3:45 — Multi-Agent Recap (45 seconds)

**You say:** "Here's the architecture. The rover's brain is a team of 9 agents across 3 machines. A Leader agent on Backboard — that's Gemini Pro — coordinates 8 teammates: a Vision agent using Gemini Flash for scene understanding, a Parser using a Qwen3 model we fine-tuned on Baseten for fast voice commands, a Safety agent that can veto unsafe moves, a Reflex agent running at 30 Hz on the Pi for emergency stops, a Mapper fusing 6 sensor types into a live occupancy grid, a Pose agent doing dead-reckoning, an STT agent running local whisper for always-on speech, and a TTS agent using ElevenLabs for voice output."

**You say:** "They coordinate through shared state, a transcript buffer, a priority arbiter, and a live spatial map. The safety agent can veto the Leader at any time. The reflex loop overrides everything if something goes wrong. It's distributed across the Pi, the laptop, and the cloud — genuine multi-agent collaboration, not chained prompts."

**Prize callout:** [Huawei — 1 Leader + 8 Teammates, distributed, task decomposition, coordination] [Backboard — orchestration harness, 17 tools, 10 features]

### 4:30 — Close

**You say:** "One API, one thread, the whole cognitive stack. The rover perceives, plans, remembers, learns from past encounters, speaks to survivors, and maps its world — all orchestrated through Backboard."

---

## Prize Track Quick Reference

| Prize | Key features to mention | When in demo |
|---|---|---|
| **Backboard** | 17 tools, RAG knowledge base, structured memory, encounter history, memory insights, teammate tools, Inner Monologue, BYOK model routing | Throughout — it's the harness |
| **Baseten** | Fine-tuned Qwen3 command parser (checkpoint-105), local STT fallback | 0:15 — voice command parsing |
| **Gemini** | Flash for vision, Pro for planning, BYOK in Backboard, scene annotations on map | 0:45 — scene understanding |
| **ElevenLabs** | Voice output to victims, async non-blocking, ~75ms latency | 1:45 and 2:45 — speaking to survivor |
| **Rox** | 6-sensor occupancy grid, log-odds fusion, dead-reckoning, Bresenham ray-casting, messy data | 0:45 — map building |
| **Huawei** | 9 agents, Leader/Teammate, distributed across 3 machines, coordination with conflict resolution | 3:45 — architecture recap |

---

## If Things Go Wrong

### Rover doesn't move
Switch to `demo_map.py` — say "Let me show you the simulated rescue scenario" and run the same narrative. The map and all visual features work identically.

### Network fails
The reflex loop keeps the rover safe with no cloud. Say "the rover's safety floor runs entirely on the Pi at 30 Hz with no network — it stops even if Wi-Fi dies." This is actually a feature, not a bug.

### Backboard API times out
The rover degrades gracefully — it stops and waits. Say "cloud calls take 1-3 seconds, so we run two loops: a fast 30 Hz safety loop on the Pi with no cloud, and a slow 1 Hz deliberative loop on Backboard. When the cloud is slow, the safety loop holds."

### TTS doesn't work
Check `ELEVENLABS_API_KEY` and `VOICE_ID` in `.env`. Test with `python -c "from voice.tts import speak; speak('test')"`.

### Map doesn't load
Check that `demo_map.py` or `main.py` is running and the MapServer is on port 8766. The frontend connects via WebSocket.

---

## Devpost Submission Checklist

- [ ] Gemini Project Number from Google AI Studio
- [ ] Select all 6 prize tracks on Devpost
- [ ] Team name and member info
- [ ] Submit by 2:00 PM EDT Saturday
