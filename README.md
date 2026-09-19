# htn2026 rover

Autonomous voice-interactive rover built at Hack the North 2026. See [CLAUDE.md](CLAUDE.md) for the full architecture and project context.

## Setup

```
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in real keys, never commit .env
```

## Running

```
python3 -m control.reflex   # fast reflex loop only
python3 -m brain.graph      # deliberative agent loop only
python3 main.py             # full stack
```
