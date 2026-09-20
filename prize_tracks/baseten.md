# Baseten — Best Use of Baseten

**Prize (per member):** Grand: SF trip + final-round interviews + $200 credits + signed *Inference Engineering*. Runner-up: AirPods 4 + $100 credits + book. 2 winners.
**Scope:** creative, meaningful use of Baseten (inference or training).

## Virtual Demo Mode — Training Pipeline

In virtual mode, the Baseten training pipeline is fully demonstrable:
- `training/scenario_generator.py` — generates disaster scenarios with messy sensor data (noise, missing readings, conflicting data)
- `training/collect_traces.py` — runs the real Backboard brain through scenarios, evaluates decisions against rescue protocols, collects good traces as JSONL
- `training/train_rescue.py` — converts traces to SFT dataset for Baseten fine-tuning
- `BASETEN_TRAINING.md` — step-by-step guide for training on Baseten H100

The model learns from itself: it runs scenarios, its good decisions become training data, it gets fine-tuned, and the improved model makes better decisions next time. Human TTS ratings (thumbs up/down) add a feedback signal to the training weights.

---

## How the rover uses Baseten

Baseten serves two roles in the rover: **command parser** (fine-tuned, actively used) and **STT** (deployed, superseded by local whisper for the live pipeline but still available as a cloud fallback).

### 1. Command parser — Qwen3-1.7B LoRA fine-tune (training + inference) — ACTIVE

This is the bigger swing: we **trained** a small model on Baseten's H100 workstations to parse natural-language voice commands into structured verb calls, so simple commands ("forward 2 meters", "turn left", "stop") execute directly without a cloud round-trip to Backboard.

- **Training:** `training/train.py` fine-tunes `Qwen/Qwen3-1.7B` with LoRA (rank 16, target modules q/k/v/o_proj) via TRL's `SFTTrainer`, 3 epochs over 552 command→verb examples (`training/dataset.jsonl`), on a single H100. Config in `training/config.py`.
- **Training run:** job `q4999dw` completed in ~67 seconds, 105 steps, producing checkpoints at steps 35/70/105 plus a final merged checkpoint.
- **Deploy:** `training/deploy_config.py` defines a `DeployCheckpointsConfig` that deploys `checkpoint-105` as a vLLM-served endpoint on H100, with `HF_TOKEN` referenced as a Baseten secret for pulling the base model weights. The endpoint is OpenAI-compatible (`/v1/chat/completions`), served under the model name `checkpoint-105`.
- **Inference:** `brain/command_parser.py` calls the deployed model's chat completions endpoint, parses the JSON verb call out of the output, and returns it to `brain/loop.py`. If the command is unrecognized or parsing fails, it returns `None` and the brain falls through to the Backboard brain for full reasoning.

The parser takes **text** as input, not audio — so it works identically whether the text comes from local faster-whisper or Baseten Whisper STT. No retraining was needed when we switched STT sources.

### 2. Whisper STT — Baseten-deployed (inference) — FALLBACK

`voice/stt.py` calls a Baseten-hosted Whisper Large V3 Turbo model directly at its predict endpoint. This was the original voice-in path (push-to-talk button → record → Baseten Whisper → text).

The live pipeline now uses **local faster-whisper** (`laptop/audio.py`) running on the laptop CPU (INT8, `base.en` model) for always-on transcription with no cloud dependency. Baseten Whisper remains as a cloud fallback and is still a valid inference deployment story.

- **Deployment fix worth mentioning to judges:** the library deploy crashed on `SecretNotFound: hf_access_token` because the base image needs to pull gated HuggingFace weights (`openai/whisper-large-v3-turbo`) and the library deploy flow doesn't expose a secrets-linking UI. We discovered secrets are team-scoped in Baseten, created the secret under the correct team path, and authored a custom Truss `config.yaml` that explicitly declares `secrets: {hf_access_token: null}` and `auth_secret_name: hf_access_token` under the `weights:` block. That's real inference engineering — we couldn't just click "deploy," we had to understand the Truss secrets mechanism and rebuild the config.

### 3. The fast path in the deliberative loop

`brain/loop.py`:

```python
if state.last_user_command:
    parsed = command_parser.parse(state.last_user_command)
    if parsed is not None:
        result = _execute_verb(parsed["verb"], parsed["args"], state, arbiter)
        state.last_user_command = None
        _update_map(state, mapper, pose_estimator, transcript_buffer)
        return state
```

So a spoken "forward 2 meters" goes: mic → local faster-whisper (or Baseten Whisper) → transcript text → Baseten fine-tuned parser → direct execution, no Backboard round-trip. That's a Baseten model in the critical path of every voice command.

---

## Integration points

| File | Role |
|---|---|
| `brain/command_parser.py` | Direct fine-tuned parser inference call (OpenAI-compatible endpoint) |
| `brain/loop.py` | Parser fast-path before falling through to Backboard |
| `voice/stt.py` | Baseten Whisper STT (cloud fallback, push-to-talk path) |
| `perception/transcript.py` | TranscriptBuffer bridging local STT to the parser |
| `training/train.py` | Qwen3-1.7B LoRA SFT via TRL |
| `training/config.py` | Baseten training project config (H100) |
| `training/deploy_config.py` | Checkpoint deployment config (vLLM on H100) |
| `training/dataset.jsonl` | 552 command→verb training examples |
| `.env` | `BASETEN_API_KEY`, `BASETEN_STT_MODEL_ID`, `BASETEN_PARSER_MODEL_ID` |

---

## Demo narrative

"The rover listens through a local whisper model running on the laptop — always-on, no button, no cloud. When someone says 'forward 2 meters,' the transcript goes to a Qwen3-1.7B model we fine-tuned on Baseten's H100 workstations to parse commands into structured verb calls — 'forward 2 meters' becomes `forward(2.0)`, executed directly without a Backboard round-trip. We also deployed Whisper Large V3 Turbo on Baseten's GPUs as a cloud STT fallback — and had to author a custom Truss config to wire the HuggingFace token through the secrets manager, because the library deploy didn't expose that. Training and inference, both meaningfully used."

The strongest single-line pitch for this track: **we trained a custom command parser on Baseten H100s and deployed both it and a Whisper model on Baseten GPUs — training and inference, both meaningfully used**.
