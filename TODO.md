# TODO — Outstanding Action Items

Everything you need to do before the demo. Ordered by what you can act on now vs what needs
a person/booth/hardware.

---

## Do Now (no blockers)

- [x] **Add `BACKBOARD_API_KEY` to `.env`** — done, key verified (integration tests pass).
- [x] **FIX: Backboard key was wrong** — fixed, integration tests pass.
- [x] **FIX: ElevenLabs TTS** — key works, audio generation verified (test fixed for bytes
      response handling).
- [ ] **Connect Gemini API key in Backboard dashboard (BYOK)** — log into Backboard, find
      provider settings, connect your Google AI Studio Gemini key. This is not in `.env` —
      it goes in the Backboard dashboard. **Or test if Backboard provides Google directly —
      see verification section below.**
- [x] **Run `truss login --browser`** — done (logged into remote baseten).
- [x] **Fix Baseten Switch env vars** — `ANTHROPIC_AUTH_TOKEN` and `BASETEN_API_KEY` added
      to `~/.config/baseten-switch/env`, switch restarted, `doctor --probe` passes (39 ok,
      0 warn).
- [x] **Install `mpv`** — already installed on Mac (`brew install mpv`). Still need on the
      Pi: `sudo apt install mpv` (run on the Pi itself, not the Mac).

---

## Baseten Booth (visit in person)

- [ ] **Redeem Baseten credits** — promo code in `#spons-baseten-2026` on the event Slack.
      Dashboard → Billing and usage → Redeem promo credits. One person redeems for the
      whole workspace.
- [ ] **Get RTX-PRO-6000 access** — your workspace is blocked from this hardware. Every
      Baseten library STT model (Whisper Large V3, Whisper Large V3 Turbo, Qwen3 ASR 1.7B)
      requires it. Tell them you're competing for their track. This is almost certainly a
      quick grant.
- [ ] **Get H100 training access** — needed for the command-parser fine-tune (Phase 5b).
      Separate from the RTX-PRO-6000 inference access. README says: "Visit the Baseten
      booth first so the team can enable training access."

Once RTX-PRO-6000 access is granted:
- [ ] **Deploy Whisper Large V3 Turbo** from https://www.baseten.co/library/whisper-large-turbo/
      → copy the model ID → put it in `.env` as `BASETEN_STT_MODEL_ID`
- [ ] **(Alternative) Deploy via Path B** — if you can't get RTX-PRO-6000 access, I can write
      a Truss `config.yaml` to deploy Whisper on cheaper hardware (L4, T4). Ask me.

Once H100 training access is granted:
- [ ] **Run the fine-tune** — `baseten train push` with the training code in `training/`
      (run.sh, train.py, dataset.jsonl are all ready). 552 examples, Qwen3-1.7B + LoRA SFT.
- [ ] **Deploy the fine-tuned checkpoint** — `baseten train checkpoint deploy --job-id <job_id>`
      → put the returned model ID in `.env` as `BASETEN_PARSER_MODEL_ID`

---

## Hardware (physical build)

- [ ] **Confirm chassis + motor driver** — DJI Robomaster, ESP32 car kit, custom base, or
      Bracket Bot base. This is the critical path for the demo.
- [ ] **Wire OAK-D camera pipeline** — `perception/camera.py` has `NotImplementedError`
      stubs for `read_detections()` and `read_frame_jpeg()`. Needs DepthAI pipeline code.
- [ ] **Wire `publish_cmd_vel` to real motors** — currently a no-op lambda in `main.py`.
- [ ] **Wire GPIO push-to-talk button** — `voice/push_to_talk.py` expects a gpiozero
      `Button(17)`. Physical button on GPIO pin 17.
- [ ] **USB webcam mic + powered speaker** — for audio capture and ElevenLabs playback.

---

## Verification (before demo)

- [x] **Verify Backboard SDK signatures** — `send_message`, `submit_tool_outputs_simple`,
      `input_image=` for vision, `call.function.arguments` (JSON str, needs json.loads).
      All verified against backboard-sdk v1.5.19. Fixes applied to `brain/backboard_client.py`.
- [x] **Smoke-test the brain loop** — brain loop integration test passes with real Backboard
      API + fake robot. Full Backboard → tool-calling → verb execution path verified.
- [x] **Test ElevenLabs TTS** — integration test passes, audio generation confirmed.
- [ ] **Test Baseten STT** — once `BASETEN_STT_MODEL_ID` is set, record a short clip and
      run `transcribe()` to confirm the response schema matches (segments[].text).
- [ ] **Test the fine-tuned parser** — once `BASETEN_PARSER_MODEL_ID` is set, run
      `command_parser.parse("forward 2 meters")` and check it returns valid JSON.

---

## Optional / MCP Setup

- [ ] **Add Baseten MCP servers** (only if you want the MCP deploy path):
      ```
      claude mcp add baseten --transport http https://api.baseten.co/mcp
      claude mcp add baseten-docs --transport http https://docs.baseten.co/mcp
      ```
- [ ] **Restart Claude Code sessions** — to pick up Baseten Switch routing
      (`baseten-switch claude on` already configured this).

---

## Admin

- [ ] **Submit prize selections on Devpost by 2:00 PM EDT Saturday** — assign one owner.
      Committed tracks: Backboard, Gemini, ElevenLabs, Baseten, Rox. openJiuwen stacks.
- [ ] **Confirm eligibility** on any track where it matters (sponsor-employee/intern rules).
- [ ] **If you hit Baseten 429s** — submit the event rate-limit form shared in
      `#spons-baseten-2026` on Slack. Retry with exponential backoff meanwhile.
- [ ] **Baseten reference repo**: https://github.com/basetenlabs/Hack-the-North-2026 —
      covers credits, Model APIs, training, Baseten Switch, and getting help.

---

## What's Already Done (no action needed)

- All brain code: `backboard_client.py` (SDK-verified against v1.5.19), `loop.py`, `tools.py`,
  `safety.py`, `state.py`
- All control code: `arbiter.py`, `reflex.py`, `controller.py`, `fake_robot.py`,
  `fake_robot_full.py`
- All perception code: `camera.py` (stubs for hardware), `vision.py` (Backboard Gemini)
- All voice code: `stt.py` (Baseten direct, schema confirmed), `tts.py` (ElevenLabs direct,
  VOICE_ID from env), `push_to_talk.py` (GPIO + wake event)
- Command parser: `brain/command_parser.py` (inference client), wired into `brain/loop.py`
  as fast-path before Backboard brain
- Training infrastructure: `training/generate_dataset.py` (552 examples),
  `training/dataset.jsonl`, `training/run.sh`, `training/train.py` (Qwen3-1.7B LoRA SFT)
- Baseten Switch: installed, configured, routing Claude Code through Baseten-hosted models
- `voice/stt.py` updated to match confirmed Baseten Whisper API (JSON + base64, not multipart)
- BUILD_PLAN.md updated with fine-tune specifics, status table, corrected sponsor checklist
- PRIZE_TRACKS.md, CLAUDE.md, BACKBOARD.md all current
- Test suites: 64 unit tests (all passing) + 9 integration tests (Backboard, ElevenLabs,
  Baseten STT, Baseten parser, brain loop). Run: `pytest -m "not integration"` (unit only)
  or `pytest -m integration` (needs real keys). Baseten tests auto-skip until model IDs are set.
