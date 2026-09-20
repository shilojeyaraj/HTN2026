# ElevenLabs — MLH Best Use of ElevenLabs

**Prize:** wireless earbuds. 1 winner.
**Scope:** natural, human-sounding, emotionally expressive voice.

---

## How the rover uses ElevenLabs

ElevenLabs is the rover's **voice out** — it's how the rover talks. Called **directly** via the ElevenLabs SDK, not routed through Backboard. This is a deliberate choice: the direct call is the stronger claim for this specific track (the judges want to see the ElevenLabs API used directly), and it's the proven, testable path right now.

> **Reverted from Backboard-routed (team decision, 2026-09-19):** Backboard's BYOK dashboard flow for connecting our own ElevenLabs key was unverified/undocumented and blocked testing. Direct SDK call is proven and testable, and it's also the stronger direct-use claim for this track. See `PRIZE_TRACKS.md` for the full reasoning.

### 1. The `speak()` tool

The brain can call `speak(text)` as one of its 10 verbs (`brain/tools.py:36`). When it does, `brain/loop.py:43` calls `voice/tts.py`'s `speak()` function, which fires ElevenLabs TTS **asynchronously** on a daemon thread — it never blocks the control loop.

### 2. Direct SDK call

`voice/tts.py`:

```python
from elevenlabs.client import ElevenLabs
from elevenlabs.play import play

_client = ElevenLabs(api_key=os.environ["ELEVENLABS_API_KEY"])
VOICE_ID = os.environ["VOICE_ID"]
MODEL_ID = "eleven_flash_v2_5"  # ~75ms latency, matters for a live demo

def _play(text: str) -> None:
    audio = _client.text_to_speech.convert(text=text, voice_id=VOICE_ID, model_id=MODEL_ID)
    play(audio)

def speak(text: str) -> None:
    threading.Thread(target=_play, args=(text,), daemon=True).start()
```

Key choices:
- **`eleven_flash_v2_5`** — the low-latency model (~75 ms), chosen because the rover narrates decisions live during the demo. A 2-second TTS latency would break the illusion that the robot is thinking out loud.
- **Direct `ElevenLabs` client** — not routed through Backboard. The rover calls `text_to_speech.convert` directly with our `ELEVENLABS_API_KEY`.
- **Daemon thread** — `speak()` returns immediately; audio plays in the background. This respects the critical rule (CLAUDE.md section 10): voice/TTS must never block the control loop.

### 3. The rescue responder voice

The system prompt (`brain/tools.py:107`) tells the brain to use `speak()` "the way a real rescue responder would: calm, clear, reassuring, brief. Narrate what matters as you find it — a hazard, an obstacle, a person — don't stay silent through something worth reporting." So the rover doesn't just speak on command; it proactively narrates what it sees as it explores, which is the "emotionally expressive, human-sounding voice" the track rewards.

### 4. Map-aware narration

With the occupancy map now live, the rover can narrate spatial discoveries: "I found a person at my 2 o'clock" or "there's rubble blocking the path ahead." The brain has access to the map's annotations, sound markers, and hazard markers through its tool schema (`get_obstacles`, `get_state`), so its spoken narration is grounded in what the map shows — not just what the camera sees in the current frame, but what the rover has accumulated over its entire path. This makes the voice output richer and more contextually aware.

Speech transcripts from the local faster-whisper STT also appear on the map as speech markers (`mapper.add_transcript`), so the operator can see where the rover heard speech and what was said — the voice-in and voice-out are both spatially anchored on the map.

---

## Integration points

| File | Role |
|---|---|
| `voice/tts.py` | Direct ElevenLabs SDK call, async playback, low-latency model |
| `brain/tools.py` | `speak` verb definition + system prompt framing |
| `brain/loop.py:43` | Routes `speak` tool calls to `voice/tts.py` |
| `control/mapper.py` | `add_transcript()` places speech markers on the map |
| `perception/transcript.py` | TranscriptBuffer bridges local STT to brain |
| `.env` | `ELEVENLABS_API_KEY`, `VOICE_ID` |

---

## Demo narrative

"The rover talks. When it finds something worth reporting — a hazard, an obstacle, a person — it calls `speak()` and you hear it in a natural voice through the speaker. We use ElevenLabs' low-latency Flash model so the narration feels live, not laggy, and it fires on a background thread so it never stalls the driving. The brain is told to narrate the way a real rescue responder would: calm, clear, brief. And now its narration is map-aware — it can tell you what it found and where, because the occupancy map gives it spatial context. Speech from the operator also appears on the map as transcript markers, so you can see where conversations happened."

The strongest single-line pitch for this track: **the rover narrates its own rescue mission out loud, in a human voice, live, with spatial awareness of what it's found and where** — and it does it through the ElevenLabs API directly.
