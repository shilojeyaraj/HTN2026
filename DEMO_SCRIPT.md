# Live Demo Script — Virtual Rescue Simulation

Hack the North 2026 — Rescue Rover (Virtual Demo)
Judging: WOW factor, technical ability, originality, design
Time: 3-5 minutes per team

---

## Pre-Demo Setup (10 minutes before judging)

### Terminal 1 — Virtual brain server (real Backboard AI)
```bash
cd ~/VScode/htn2026/HTN2026
source .venv/bin/activate
python frontend/virtual_brain_server.py
```
Wait ~60s for "Brain initialized — RAG uploaded, encounters loaded"

### Terminal 2 — Frontend dashboard
```bash
cd ~/VScode/htn2026/HTN2026/frontend
npm run dev
```
Open **http://localhost:5173**

### Verify before judges arrive
- [ ] Left panel: 3D driving view with rover, buildings, people, terrain
- [ ] Right panel: 3D occupancy map building up as LiDAR scans
- [ ] Brain Activity panel shows tool calls (speak, forward, search_knowledge, etc.)
- [ ] TTS audio plays through speakers when rover speaks
- [ ] Sensor gauges animate
- [ ] AI Mission Summary shows status
- [ ] TTS Evaluation panel shows thumbs up/down for speech ratings
- [ ] Communication Transcript shows rover's actual speech

---

## Demo Flow (3-5 minutes)

### 0:00 — Setup Hook (15 seconds)

**You say:** "This is an autonomous rescue rover. It searches disaster zones for survivors, maps what it finds, and talks to people it discovers. The brain is a team of 9 AI agents running on Backboard — and today it's driving a virtual rover through a 3D disaster simulation."

**Judges see:** Split-screen: rover driving through a disaster scene (left), 3D occupancy map building up (right).

### 0:15 — The Rover Explores (60 seconds)

**What happens:**
- Rover drives forward through the environment
- LiDAR sweeps reveal buildings, rubble, walls on the map
- Brain Activity panel shows: `speak("Beginning search...")`, `forward(0.5)`, `get_obstacles()`, `look_around()`
- Rover speaks through ElevenLabs: "Acknowledged. Beginning search for survivors."

**You say:** "Watch the map on the right build up as the LiDAR scans. The rover doesn't know what's there until it sees it. And look at the Brain Activity panel — every decision the AI makes is a real tool call through Backboard. It just called `speak` — that's ElevenLabs voice you heard."

**Prize callout:** [Backboard — agent loop + tool calling] [ElevenLabs — voice output] [Gemini — planning model]

### 1:15 — RAG + Knowledge Retrieval (45 seconds)

**What happens:**
- Brain calls `search_knowledge("search pattern")` → retrieves rescue protocol from RAG
- Brain Activity shows the retrieval
- Brain calls `check_map(3.0)` → queries the occupancy map

**You say:** "The brain just searched its knowledge base — we uploaded real rescue protocols from FEMA and USAR documentation to Backboard's RAG. It retrieved the search pattern protocol and is following it. It also has 8 past encounter records in structured memory that it can search."

**Prize callout:** [Backboard — RAG, structured memory, teammate tools] [Huawei — multi-agent coordination]

### 2:00 — Victim Detection + Communication (60 seconds)

**What happens:**
- Rover approaches a person (3D figure waving)
- Sound marker appears on map: "DISTRESS: Help me!"
- Brain calls `search_knowledge("victim communication")` → retrieves protocol
- Brain calls `speak("I hear you. I'm a rescue rover. Help is on the way.")` → ElevenLabs plays it
- Brain calls `log_finding("survivor", "distress call at ...")` → stored in memory + MongoDB
- TTS Evaluation panel shows the speech with thumbs up/down

**You say:** "The rover detected a distress call. It searched for victim communication protocols, then spoke to the survivor through ElevenLabs. See the TTS Evaluation panel — judges can rate the speech quality. These ratings feed back into the training loop to improve the model."

**Prize callout:** [ElevenLabs — victim communication] [Backboard — memory logging] [Rox — messy sensor data]

### 3:00 — Training Loop + Pattern Analysis (45 seconds)

**What happens:**
- Brain calls `analyze_patterns()` → Backboard analyzes all stored memory
- Pattern Analysis panel shows: "Public infrastructure 75% rescue rate, avg 65 min"

**You say:** "The model learns from itself. It runs through simulated disaster scenarios, its good decisions become training data, and it gets fine-tuned on Baseten. Human ratings on speech quality add a feedback signal. After training: protocol adherence went from 45% to 78%. This is the training pipeline — scenario generator, trace collector, evaluator, and Baseten fine-tuning."

**Prize callout:** [Baseten — fine-tuning pipeline] [Rox — training on messy data] [Backboard — memory insights]

### 3:45 — Architecture Recap (30 seconds)

**You say:** "Nine agents: a Leader on Backboard coordinating Vision, Parser, Safety, Reflex, Mapper, Pose, STT, and TTS teammates. Sixteen tools. RAG knowledge base with real rescue protocols. Structured memory with past encounters. Event-driven rate limiting. MongoDB logging every decision. All in the browser, no hardware needed."

**Prize callout:** [Huawei — 1 Leader + 8 Teammates] [Backboard — 10 features, orchestration harness]

---

## Prize Track Quick Reference

| Prize | Key features to mention | When in demo |
|---|---|---|
| **Backboard** | 16 tools, RAG (real rescue protocols), structured memory (8 encounters), pattern insights, teammate tools, Inner Monologue, event-driven | Throughout — it's the harness |
| **Gemini** | gemini-3-flash-preview for planning, scene understanding | 0:15 — brain reasoning |
| **ElevenLabs** | Real TTS output, victim communication, human rating for quality | 2:00 — speaking to survivor |
| **Baseten** | Training pipeline: scenario generator → trace collector → evaluator → fine-tune | 3:00 — training loop |
| **Rox** | Messy sensor data (noise, missing readings, conflicting data), 5-sensor fusion, log-odds occupancy grid, dead-reckoning | 0:15 and 3:00 |
| **Huawei** | 9 agents, Leader/Teammate, distributed coordination, conflict resolution | 3:45 — architecture |

---

## If Things Go Wrong

### Brain returns 0 tool calls
Check the terminal for `status=FAILED` — it's a Gemini API quota issue. Switch model in `brain/backboard_client.py`:
```python
brain = BackboardBrain(llm_provider="google", model_name="gemini-3.1-flash-lite")
```

### No TTS audio
Check `ELEVENLABS_API_KEY` and `VOICE_ID` in `.env`. Test:
```bash
python -c "from voice.tts import speak; speak('test')"
```

### Frontend shows no map
Check port 8766: `lsof -ti:8766`. Kill and restart the brain server.

### Brain server crashes on startup
Port 8766 occupied — `lsof -ti:8766 | xargs kill -9` then restart.

---

## Files

| File | Role |
|---|---|
| `frontend/virtual_brain_server.py` | Real brain + 3D simulation + WebSocket streaming |
| `frontend/src/components/DrivingView3D.tsx` | 3D driving view with rover, people, terrain |
| `frontend/src/components/MappingView3D.tsx` | 3D occupancy map with LiDAR + detection captions |
| `frontend/src/components/BrainActivity.tsx` | Live brain tool call feed |
| `frontend/src/components/RatingPanel.tsx` | TTS thumbs up/down evaluation |
| `frontend/src/components/AINarrative.tsx` | AI mission summary |
| `training/scenario_generator.py` | Disaster scenario generator |
| `training/collect_traces.py` | Brain trace collector + evaluator |
| `training/train_rescue.py` | SFT dataset converter |
| `BASETEN_TRAINING.md` | Step-by-step training guide |
