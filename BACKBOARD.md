# BACKBOARD.md

How the rover's brain runs on Backboard.io. Companion to CLAUDE.md.
Read this before designing the deliberative loop.

**Verified 2026-09-19 against docs.backboard.io.** Sections 4, 6-9 below were corrected
against the live docs — the original draft had two wrong assumptions: the entry point is
`send_message`, not `create_assistant`/`create_thread`/`add_message`; and `system_prompt`
is NOT persisted at the assistant level, it must be re-sent on every call (which actually
matches the fixed-prefix caching rule we already wanted). A couple of narrower details
are still marked **VERIFY** — confirm those specifically before relying on them.

---

## 1. What Backboard is

Backboard is the full AI stack behind one API key: model routing across 17,000+ LLMs, persistent memory, agentic RAG, parallel tool calling, voice (speech-to-text, text-to-speech, and audio-to-audio), image, web search, and stateful threads. One integration replaces what would otherwise be four or five vendors (a model gateway, a memory service, a voice provider, an orchestration framework).

**We use Backboard as the rover's slow deliberative brain.** It does not touch the fast reflex loop (see section 10).

---

## 2. Scope for this project

- **Primary: LLM routing.** Assign different models to different roles, chosen per message inside one thread.
- **Primary: voice routing.** Speech-to-text in, text-to-speech out, with Backboard picking the voice provider (it can route to ElevenLabs or OpenAI voices).
- **Optional, high value: memory.** One parameter (`memory="Auto"`) turns on persistent cross-thread memory. Best demo beat on the platform. Decide whether to include (section 9).
- **Available but not planned:** RAG, image generation, web search. Only add if a feature clearly needs them.

---

## 3. Core objects and concepts

- **Assistant:** identified by `assistant_id`. Memory (if enabled) lives at the assistant level and persists across all of that assistant's threads. The system prompt is **not** stored on the assistant — see below.
- **Thread:** identified by `thread_id`, a stateful conversation. Both `thread_id` and `assistant_id` are optional on `send_message` — omit them and Backboard auto-creates a thread (and assistant) for you; pass them back in to continue the same mission/session.
- **Message:** sent via `send_message`. Can carry file attachments (camera frames, documents via the `files` param), a per-call `system_prompt`, and a per-call model. Returns text and/or tool calls.
- **System prompt is NOT persisted.** `system_prompt` is "instructions for this turn" only — it must be re-passed on every `send_message` call. This is actually convenient: it's exactly the fixed prefix we want at the top of every call for prompt caching anyway (CLAUDE.md section 7).
- **Tools:** function definitions passed directly on `send_message` (`tools=[...]`), same JSON schema shape as OpenAI function-calling. Backboard supports parallel tool calls. The brain returns tool calls; we execute them on the robot and submit the outputs back via `submit_tool_outputs_simple`.
- **Memory modes:** `memory="Auto"` (extract facts and retrieve automatically), `"Readonly"`, or `"off"` (default). A separate higher-accuracy `memory_pro` mode exists; `memory` and `memory_pro` cannot be used together. Memory persists by `assistant_id`, so keep that stable across the mission.
- **Model routing:** pass `llm_provider` (e.g. `openai`, `anthropic`, `google`) and `model_name` per call. Defaults are `openai` / `gpt-4o` if omitted — always set both explicitly for our per-role routing.
- **Voice:** speech-to-text and text-to-speech are routed via a `voice={"stt": {...}}` / `voice={"tts": {...}}` dict passed to the same `send_message` call (see section 8) — not separate calls. Audio-to-audio realtime is a distinct API (`connect_realtime`), not used here (section 8 gotcha).

---

## 4. SDK quickstart (Python) — verified

```
pip install backboard-sdk
```

```python
from backboard import BackboardClient

client = BackboardClient(api_key="...")  # read from env, never hardcode

response = await client.send_message(
    content="<scene description or user command>",
    system_prompt="<fixed rover operating instructions>",  # re-sent every call, not persisted
    llm_provider="google",
    model_name="gemini-2.5-pro",          # VERIFY exact current slug before use
    tools=[...],                          # the tool schema from section 6
    thread_id=thread_id,                  # None on first call; carry forward after
    assistant_id=assistant_id,            # None on first call; carry forward after
    memory="Auto",                        # omit or "off" if not using memory
)
```

There is no separate `create_assistant`/`create_thread` step for our flow — `send_message` auto-creates both on the first call when `thread_id`/`assistant_id` are omitted; capture the returned ids and pass them back in on every subsequent tick to keep one mission thread. `send_message` also supports `stream`, `json_output`, and a `thinking` dict on reasoning models. There is $10 in free credits on signup, plus whatever the event provides. An MCP server is also available.

Env var (our convention): `BACKBOARD_API_KEY`.

---

## 5. Architecture mapping: Backboard as the deliberative brain

The two-loop design from CLAUDE.md is unchanged. The fast reflex loop stays onboard, classical, and owns `cmd_vel`. Backboard is the ~1 Hz deliberative layer only.

**Per-role model routing (all in one thread, model chosen per message):**

| Role | Model type | Input | Output |
| --- | --- | --- | --- |
| Scene understanding | vision-capable model | camera frame + detections | structured scene |
| Planning | strong reasoning model | scene + goal + user command | tool calls |
| Safety sanity-check (optional) | small fast model | planned action + detections | OK / veto |

Routing distinct roles to distinct models is not just efficient, it is a genuine heterogeneous multi-agent setup, which is also what the Huawei openJiuwen track rewards.

---

## 6. Tool schema (the brain's actions on the robot)

Define these as Backboard tools on the assistant. The planning model calls them; we execute them on the robot and submit the results back.

```
set_goal(x: float, y: float)      # navigate to a point
set_heading(degrees: float)       # turn to face a bearing
set_speed(mps: float)             # cap forward speed
stop()                            # halt
speak(text: str)                  # say something (routes to TTS)
```

Keep the schema small and stable so the fixed prompt prefix stays cacheable.

---

## 7. Deliberative tick (using Backboard) — verified shape

Runs at ~1 Hz, independent of the reflex loop. Two roles, so two `send_message` calls per
tick (scene understanding, then planning) — the safety check stays classical and local
(`brain/safety.py`), it does not need its own LLM round-trip.

```python
# 1. scene understanding — vision model, frame attached via `files`
scene_resp = await client.send_message(
    content="Describe obstacles, free space, and hazards.",
    system_prompt=FIXED_PREFIX,
    llm_provider="google", model_name="gemini-2.5-pro",   # VERIFY slug
    files=[frame_path],                                    # VERIFY: SDK equivalent of
                                                             # multipart `files=` upload —
                                                             # confirmed at the raw HTTP
                                                             # level, confirm the SDK
                                                             # wrapper takes the same kwarg
    thread_id=thread_id, assistant_id=assistant_id,
)

# 2. planning — reasoning model, tool calls, same thread so history carries over
plan_resp = await client.send_message(
    content=f"Scene: {scene_resp.content}\nGoal: {goal}\nUser: {last_user_command}",
    system_prompt=FIXED_PREFIX,
    llm_provider="google", model_name="gemini-2.5-pro",
    tools=PLANNER_TOOLS,
    thread_id=thread_id, assistant_id=assistant_id,
    memory="Auto",  # if enabled
)

if plan_resp.status == "REQUIRES_ACTION":
    tool_outputs = [execute_on_robot(tc) for tc in plan_resp.tool_calls]
    plan_resp = await client.submit_tool_outputs_simple(
        thread_id=plan_resp.thread_id, tool_outputs=tool_outputs,
    )
```

Steps: snapshot inputs -> scene call -> planning call -> classical safety veto
(`brain/safety.py`, no network) -> execute the surviving action on the robot (goal/velocity
to the controller, never raw motor commands) -> submit tool outputs -> if `speak()` was
called, fire text-to-speech asynchronously (never block the tick).

Throttle to ~1 Hz, retry errors with exponential backoff, keep `FIXED_PREFIX` identical
across calls for caching (it is never persisted server-side, section 3), and degrade
safely (slow or stop) if a call fails.

---

## 8. Voice path — verified shape

Push-to-talk (hold a button). STT and TTS are both just a `voice` dict on `send_message`,
not separate endpoints:

```python
# speech-to-text: audio in, transcript used as the LLM input for that same call
stt_resp = await client.send_message(
    audio_file="command.wav",
    voice={"stt": {"provider": "openai", "model": "gpt-4o-mini-transcribe"}},
    llm_provider="openai", model_name="gpt-4o-mini", send_to_llm="true",
)

# text-to-speech: LLM reply synthesized to audio
tts_resp = await client.send_message(
    content=reply_text,
    voice={"tts": {"provider": "elevenlabs", "model": "scribe_v2", "voice": "<voice_id>"}},
    llm_provider="openai", model_name="gpt-4o-mini", send_to_llm="true",
)
```

Providers mix independently per leg — e.g. ElevenLabs for STT (`"provider": "elevenlabs"`)
with OpenAI TTS unchanged, or vice versa. **VERIFY** whether `tools=` can be combined with
`voice=` in the same call (i.e. STT -> tool-calling planner -> TTS in one round trip); if
not, keep it as three explicit `send_message` calls (STT, then the tool-calling planner
call from section 7, then TTS on the reply text) sharing the same `thread_id`.

**GOTCHA: do not use `connect_realtime` (audio-to-audio) for the robot.** The rover has to
act, and actions are tool calls that live in the text layer of `send_message`/
`submit_tool_outputs_simple`. `connect_realtime` is a separate native realtime pipeline for
pure conversation with no tool-calling path documented — use STT -> text -> TTS instead.

All voice I/O is async and off the reflex loop, so audio never stalls the wheels.

---

## 9. Memory (optional, highest reward per line of code)

`memory="Auto"` on messages turns on persistent memory. It is assistant-level and survives across threads, and it auto-extracts facts. Demo hook: "remember this spot as the kitchen," drive away, then "take me back to where you saw the red mug." If enabled, decide what facts matter: named locations, objects seen and where, and user commands.

Optional for our scope, but it is Backboard's flagship feature and the single strongest demo moment. Recommended if time allows.

---

## 10. Constraints and rules (the agent MUST follow)

- **Backboard is a cloud API, so it is the slow deliberative loop only. NEVER put it in the fast reflex loop.**
- The onboard classical reflex loop runs at ~30 Hz and has final authority over `cmd_vel`.
- Voice, speech-to-text, and text-to-speech are all async, never blocking the control loop.
- ~1 Hz on the deliberative loop, exponential backoff on errors, graceful degrade if the network drops.
- Keys come from environment variables, never committed.
- Manage credits from one workspace so the team shares them.

---

## 11. Track alignment

- **Backboard track** rewards using as much of the stack as possible. Routing + voice + tool calling already cover a lot; adding memory (and optionally image/RAG/web search) widens it.
- **Huawei openJiuwen** stacks cleanly: per-role model routing is a real heterogeneous multi-agent system. Frame scene, planner, and safety as coordinating agents.

---

## 12. Still to verify before coding

Resolved against `docs.backboard.io` on 2026-09-19: per-message model/provider selection
(`llm_provider` + `model_name`), tool schema and the submit-tool-outputs flow
(`tools=` + `submit_tool_outputs_simple`), voice call shape (`voice={"stt"/"tts": {...}}`
on `send_message`), and memory params (`memory="Auto"/"Readonly"/"off"`).

Still open — confirm these specifically before relying on them, ideally by installing
`backboard-sdk` and checking `inspect.signature`, since the docs describe the raw HTTP API
more completely than the Python wrapper:

- Whether the SDK's `send_message` takes `files=[...]` (paths/file-like objects) the same
  way the raw multipart HTTP endpoint does for vision input — confirmed at the HTTP level
  (`files=[("files", open("photo.jpg", "rb"))]`), not confirmed for the SDK wrapper.
- Whether `tools=` and `voice=` can be combined in one `send_message` call (section 8).
- Current model slugs to use for the vision and reasoning roles (docs examples use
  `gpt-4o` / `claude-sonnet-4-20250514`; confirm what's actually routable and fast enough
  at demo time via `client.list_models()` / `list_by_provider`).

Docs: `docs.backboard.io`, full index at `backboard-docs.docsalot.dev/llms.txt`. SDK:
`backboard-sdk` on PyPI. MCP server available.
