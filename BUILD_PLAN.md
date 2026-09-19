# BUILD_PLAN.md

Concrete build plan to hit the five committed tracks in PRIZE_TRACKS.md, on top of the
two-loop architecture in CLAUDE.md. This supersedes the model-role assignment in
CLAUDE.md section 6 (Gemini was the planner there; PRIZE_TRACKS moves it to vision to
avoid the Backboard overlap trap). CLAUDE.md's reflex loop and shared-state design are
unchanged.

**2026-09-19 update:** CLAUDE.md was rewritten with a literature-informed drive layer
(Code as Policies / SayCan / Inner Monologue) and now specifies bounded, self-completing
verbs (`forward`/`backward`/`turn`/`stop`/`speak`/`get_obstacles`/`get_state`) instead of
the earlier `set_goal`/`set_heading`/`set_speed` schema, plus a priority-mux arbiter with
a watchdog between the brain and the reflex loop, and drops LangGraph in favor of a plain
`brain/loop.py`. This is now implemented: `brain/tools.py` (verb schema), `brain/loop.py`
(replaces `graph.py` + `planner.py`), `control/arbiter.py` (new), `control/reflex.py` and
`control/controller.py` (rewritten), `brain/backboard_client.py`'s tool loop now submits
each verb's *real* completion status back to Backboard instead of a trivial ack, which is
what makes Inner Monologue actually work. NoMaD/ViNT (CLAUDE.md section 7) stays deferred
until chassis/compute is confirmed. Sections 1-3 below (role map, sponsor tracks) are
still accurate; treat the file-level details in the delta table and phase descriptions
below as describing the pre-rewrite shape unless a section says otherwise.

**Resolved 2026-09-19:** the earlier "Baseten = fine-tuned vision model, voice-in via
Backboard" plan (still described in section 1's table and its "Revised" note below) has
been reverted, per CLAUDE.md section 4: **Baseten = direct STT** (Whisper Large V3 Turbo,
its own dedicated predict endpoint) is the track-qualifying slice again; the fine-tune is
now an optional, deferred command-parser side quest (CLAUDE.md section 13), not
implemented. `perception/finetuned_vision.py` has been removed; `voice/stt.py` now calls
Baseten directly. Section 1's role-map table and the "Revised" paragraph after it are
stale as a result — treat this note as the current truth for Baseten/voice-in until
someone rewrites that table.

**Resolved 2026-09-19 (later same day):** Gemini and ElevenLabs now route through
Backboard too (BYOK — our own API keys, connected in the Backboard dashboard, not read by
this app's code), per PRIZE_TRACKS.md's 2026-09-19 team decision. Implemented:
`brain/backboard_client.py` gained `describe()` (vision, `files=[image_path]` +
`llm_provider="google"`) and `speak_to_url()` (TTS, `voice={"tts": {"provider":
"elevenlabs", ...}}`, returns an `audio_url` read from `response.messages[i]
["voice_records"]["tts"]["audio_url"]` per the verified docs). `perception/vision.py` and
`voice/tts.py` were rewritten against these; `brain/llm_client.py` (the direct
OpenAI-compatible Gemini client) and the `elevenlabs`/`openai` SDK dependencies are gone.
Baseten voice-in stays direct (unchanged) since Backboard doesn't document Baseten as a
voice provider. **VERIFY** two things before the demo: whether `send_to_llm="false"`
actually makes TTS synthesize the given text verbatim rather than a model-generated reply
to it (the docs only confirm the latter is the default behavior), and the SDK's `files=`
kwarg for vision against the installed `backboard-sdk` version. `.env.example` now only
lists vars this app's code actually reads (`BACKBOARD_API_KEY`, `BASETEN_API_KEY`,
`BASETEN_STT_MODEL_ID`) — `GEMINI_API_KEY`/`ELEVENLABS_API_KEY` still need to be obtained,
but go into the Backboard dashboard, not `.env`.

---

## 1. Target role -> provider map (final, per PRIZE_TRACKS.md)

| Role | Provider | Direct or via Backboard | Sponsor track it proves |
| --- | --- | --- | --- |
| Scene / vision understanding | **Gemini API** | Direct | MLH: Best Use of Gemini API |
| Planner (tool-calling brain) | **Backboard** (`send_message`, tools, thread state, memory) | Backboard | Backboard: Built on Backboard |
| Voice in (STT) | **Backboard**'s own STT routing (`voice={"stt": ...}`) | Backboard | Backboard: Built on Backboard (widens stack usage) |
| Safety monitor | Classical distance check | Neither (no cloud) | — (keeps reflex-adjacent logic honest, doesn't compete for a track) |
| Real-world fine-tuned vision model | **Baseten**, fine-tuned on rover-captured footage, deployed for inference | Direct | Baseten: Best Use of Baseten |
| Voice out (TTS) | **ElevenLabs** | Direct | MLH: Best Use of ElevenLabs |
| Reflex loop | Classical, onboard | Neither | Safety floor for every other track's demo |

**Revised 2026-09-19:** Baseten's slice moved from STT to a model fine-tuned on footage
the rover itself captures and deployed on Baseten for inference — a stronger, more
literal claim on that track's "inference or training" scope, and it ties Baseten to the
robot's own embodiment story instead of a generic Whisper deploy. Voice-in moved to
Backboard's own STT routing to fill the gap, which also deepens the Backboard track's
"how much of the stack do you use" story. See PRIZE_TRACKS.md's Baseten and Backboard
entries for the reasoning.

This is still a reversal from the original repo, which had Gemini as the planner and
Baseten (Kimi) as the vision agent — that pairing was exactly the "overlap trap"
PRIZE_TRACKS.md warns about (Gemini not visibly used, Baseten and Backboard both claiming
the brain).

Rox (no code, pitch framing) and Huawei openJiuwen (no new code, framing of the existing
scene -> planner -> safety handoff as multi-agent coordination) ride on this same pipeline
for free — see section 5.

---

## 2. Delta from the current repo

| File | Current state | Change needed |
| --- | --- | --- |
| `brain/llm_client.py` | `SCENE_AGENT`=Baseten Kimi, `SAFETY_AGENT`=Baseten GLM (unused), `PLANNER_AGENT`=Gemini | Drop `PLANNER_AGENT` and `SAFETY_AGENT` (safety.py never called an LLM anyway). Repoint `SCENE_AGENT` to `gemini_client(...)`. Add `backboard_client.py` (new) for the planner. |
| `brain/backboard_client.py` | doesn't exist | New. Thin wrapper: holds `BACKBOARD_API_KEY`, `thread_id`/`assistant_id` state across ticks, exposes `send_message(...)` and a `run_tools(...)` helper that loops `send_message` -> `submit_tool_outputs_simple` until `status == "COMPLETED"`. |
| `brain/planner.py` | Calls `PLANNER_AGENT` (Gemini) directly with OpenAI tool-calling | Rewrite to call `backboard_client.run_tools(content=..., system_prompt=SYSTEM_PROMPT, tools=PLANNER_TOOLS, memory="Auto")`. Tool schema (`PLANNER_TOOLS`) stays identical — Backboard's tool JSON shape matches OpenAI's. |
| `perception/scene_agent.py` | Calls `SCENE_AGENT` (currently Baseten Kimi) | No structural change — just benefits from `SCENE_AGENT` now pointing at Gemini in `llm_client.py`. Confirm Gemini's OpenAI-compat endpoint accepts the same `image_url` content-block shape already used here (it does, per Gemini's OpenAI compatibility docs — re-confirm the exact vision model slug before the demo). |
| `brain/graph.py` | `scene_node` is a passthrough stub (never calls `describe_scene`); `planner_node` calls `plan()` | Wire `scene_node` to actually call `perception.scene_agent.describe_scene(frame, detections)` and set `state.scene_description`. `planner_node`/`safety_node` otherwise unchanged. |
| `voice/tts.py` | ElevenLabs direct, async thread | No structural change. Pick and hardcode a real `voice_id` before demo day (currently placeholder `"Rachel"`). |
| `voice/stt.py` | `NotImplementedError` stub | Implement via `BackboardBrain.transcribe(audio_path)` (new method on the same class from Phase 2) — `send_message(audio_file=..., voice={"stt": {"provider": "openai", "model": "gpt-4o-mini-transcribe"}})`, sharing the mission `thread_id`. `record_while_held` stays a stub — real mic capture is hardware-blocked like the camera. |
| `perception/finetuned_vision.py` | doesn't exist | New. Generic POST to the fine-tuned model's dedicated Baseten predict endpoint (`https://model-<id>.api.baseten.co/environments/production/predict`) — not the shared LLM gateway. Input/output schema is genuinely unknown until the model is fine-tuned and deployed (depends on what footage gets captured/labeled), so this stays a thin, generic wrapper until then. |
| `main.py` | Wires reflex thread + LangGraph tick | Add `BACKBOARD_API_KEY` to the loaded env vars; pass the persistent `thread_id`/`assistant_id` from `backboard_client` into `RobotState` (or module-level) so the planner keeps one mission thread across ticks, which is what makes `memory="Auto"` actually useful. |
| `.env.example` | `BASETEN_API_KEY`, `GEMINI_API_KEY`, `ELEVENLABS_API_KEY` | Add `BACKBOARD_API_KEY`. |
| `requirements.txt` | `langgraph`, `openai`, `depthai`, `elevenlabs`, `python-dotenv`, `numpy` | Add `backboard-sdk`. |

`brain/state.py` and `control/*` are untouched — the two-loop contract (brain never
touches motors, reflex always wins) doesn't change.

---

## 3. Phased build order (each phase is a standalone, demoable checkpoint)

Matches PRIZE_TRACKS.md's build order, made concrete. If time runs out, stop after any
phase and the demo still works — later phases are additive, not dependencies.

**Phase 0 — already done:** repo scaffold, reflex loop skeleton, controller math,
LangGraph skeleton, ElevenLabs TTS thread. (This is the current repo state.)

**Phase 1 — robot drives, reflex-only.**
- Get real depth/detections flowing from `perception/camera.py` (OAK-D pipeline is still
  a TODO stub) into `control/reflex.py`.
- Confirm chassis + motor driver (CLAUDE.md open TODO) and wire `publish_cmd_vel` to real
  motors instead of the current no-op lambda in `main.py`.
- **Exit test:** robot stops/avoids with zero network connectivity. This is the safety
  floor every later phase's demo depends on.

**Phase 2 — Backboard brain online.**
- Add `brain/backboard_client.py`, rewrite `brain/planner.py` against it (section 2).
- Wire real `state.current_goal` / `state.last_user_command` into the planner call.
- **Exit test:** a hardcoded scene description + a typed fake user command produces a
  correct tool call end-to-end through Backboard, and the robot moves accordingly.
  Qualifies **Backboard** and (by pitch framing only) **Rox**.

**Phase 3 — Gemini vision online.**
- Repoint `SCENE_AGENT` to Gemini, wire `scene_node` in `brain/graph.py` to call it with
  real camera frames.
- **Exit test:** scene description in the logs visibly reflects what the camera actually
  sees. Qualifies **Gemini**.

**Phase 4 — ElevenLabs voice out. DONE.**
- `voice/tts.py` calls `text_to_speech.convert(voice_id=..., model_id="eleven_flash_v2_5")`
  and plays it with `elevenlabs.play.play`. `speak()` is fired from `brain/planner.py`
  whenever the planner's tool calls include `speak()` (wired in Phase 2), not from
  `main.py` anymore.
- `eleven_flash_v2_5` chosen for ~75ms latency over `eleven_v3`/`eleven_turbo_v2_5`
  (deprecated) — matters live, since narration shouldn't lag behind the decision.
- **Gotcha confirmed:** `elevenlabs.play.play()` shells out to `mpv`/`ffplay` — needs
  `sudo apt install mpv` on the Pi, it is not a pure-Python playback path.
- **Still TODO:** swap the placeholder `VOICE_ID` in `voice/tts.py` for a voice actually
  picked from the ElevenLabs dashboard.
- **Exit test:** robot narrates a decision out loud during a live run. Qualifies
  **ElevenLabs**.

**Phase 5a — Backboard voice-in (STT).**
- Add `BackboardBrain.transcribe()`, implement `voice/stt.py` against it, wire push-to-talk
  capture to it, feed the transcript into `state.last_user_command` for the next tick.
- **Exit test:** a spoken command changes the robot's next action. Deepens **Backboard**.

**Phase 5b — Baseten fine-tuned vision model.**
- Capture real-world video/frames from the rover's camera at the event (however much time
  allows — this determines what's realistic to fine-tune on).
- Fine-tune a small vision model on that footage on Baseten's H100 workstations (visit the
  booth to enable), deploy it on Baseten.
- Implement `perception/finetuned_vision.py` against the deployed model's real predict
  endpoint and output schema (unknowable until it exists — see section 2).
- Wire its output into `RobotState` (new field, e.g. `venue_model_output`) and into
  `brain/planner.py`'s prompt content, alongside the Gemini scene description.
- **Exit test:** the planner's context visibly includes a label/classification the
  fine-tuned model produced from the rover's own footage. Qualifies **Baseten**.
- **Risk:** this is the highest-uncertainty phase — data capture, labeling, and a
  fine-tuning job all have to happen live. If time is short, cut this phase; Backboard,
  Gemini, and ElevenLabs are unaffected since they don't depend on it.

**Phase 6 — Framing and stretch add-ons.**
- No new code required for **openJiuwen**: write up the scene -> planner -> safety
  handoff as genuine multi-agent coordination (task decomposition + tool use +
  coordination) for the pitch and README.
- Optional stretch, only if the above is solid and stable: Bracket Bot hardware base,
  Tiger Data telemetry dashboard (both independent of the brain stack, per
  PRIZE_TRACKS.md, so they don't risk phases 1-5).

---

## 4. Verify before/while coding (carried over + new)

- Current Gemini vision model slug to use directly (not just via Backboard) — check
  `ai.google.dev` for the live multimodal model name at build time.
- Baseten Whisper Large V3 Turbo's actual request/response schema once deployed — Truss
  models vary; don't assume it matches Whisper's HF pipeline output verbatim.
- From BACKBOARD.md section 12, still open: whether `backboard-sdk`'s `send_message`
  takes `files=[...]` for vision the same way the raw HTTP multipart endpoint does (moot
  now for the vision role since Gemini is direct, but still relevant if scene description
  text is ever attached as a file to the Backboard planner call instead of inlined as
  `content`), and whether `tools=` and `voice=` can combine in one Backboard call.
- Confirm ElevenLabs `voice_id` and Baseten model deployment before demo day; both need a
  one-time setup step (voice picked in ElevenLabs dashboard, model deployed from Baseten
  library) that isn't just an env var.

---

## 5. Sponsor-track checklist (what a judge needs to actually see)

- **Backboard:** thread/tool-call logs showing planner routing + voice-in (STT) +
  (recommended) `memory="Auto"` demo beat — e.g. "remember this spot," drive off, "take me
  back."
- **Gemini:** scene description output visibly driven by the live camera feed, not canned.
- **ElevenLabs:** the robot audibly narrating a decision or answering a spoken command
  during the live demo.
- **Baseten:** the fine-tuned model's output (a label/classification from footage the
  rover itself captured) visible in the planner's context, plus the training story
  (booth visit, H100 fine-tuning job) told in the pitch.
- **Rox / Huawei openJiuwen:** no separate artifact — these are won in the pitch, framing
  the same pipeline (noisy real-world sensor data -> agent decisions under uncertainty;
  scene/planner/safety as coordinating agents).

---

## 6. Admin

- Prize selections due on Devpost by **2:00 PM EDT Saturday** — assign one owner now
  (CLAUDE.md / PRIZE_TRACKS.md don't currently name one).
- Re-run `pip install -r requirements.txt` after adding `backboard-sdk`.
