# Broker

A voice-driven cyberpunk extraction game. You're a neural operative embedded in
Syndicate territory; **N.O.V.A.**, an AI implant powered by Claude, acts as your
guide and game master. Talk to NOVA out loud to navigate the city, earn credits,
solve hacking puzzles, negotiate with NPCs, buy the Syndicate Decryption Key, and
escape from The Extraction Rooftop.

## How it plays

- **Speak** to NOVA — your microphone audio is transcribed and drives the game.
- NOVA **talks back** via the browser's built-in speech synthesis.
- A live HUD tracks your callsign, location, health, and credits.
- An in-game **Field Manual** explains the locations, actions, and win path.

Win condition: earn **400 credits**, buy the **Syndicate Decryption Key** at The
Black Market, then travel to **The Extraction Rooftop** (locked until you hold the
key) and board the shuttle.

## Architecture

```
Browser (client/)                 Backend (FastAPI)                 External
─────────────────                 ─────────────────                 ────────
mic → VAD → WS  ───audio───▶  /stream  → STT (Deepgram) ──▶ transcript
                              ↓
HUD ◀── /state (poll) ──   intent classifier → ConstrainedLLM ──▶ Claude (Anthropic)
speech synth ◀── "speak" ──   tool dispatch → game state (DB)
```

- **`main.py`** — FastAPI app + CORS; initializes the DB on startup.
- **`broker/router.py`** — the `/stream` WebSocket (audio in, UI/voice out) and
  the `/state` HUD endpoint. Owns the per-session lifecycle.
- **`integrations/`** — `stt.py` (Deepgram streaming STT), `llm.py` (Claude
  cognition + server-authoritative tool dispatch), `classifier.py` (fast
  ambient-vs-LLM routing).
- **`mcp_server.py`** — game-state helpers and session create/reset/delete.
- **`db.py`** — database abstraction: PostgreSQL (prod) or SQLite (dev).
- **`client/`** — static frontend (`index.html`, `app.js`, `vad.js`, `style.css`).

## Tech stack

- **Backend:** Python · FastAPI · WebSockets · gunicorn/uvicorn
- **AI:** Claude (Anthropic) for cognition · Deepgram for streaming STT · browser
  Web Speech API for TTS
- **Data:** PostgreSQL via `psycopg` v3 (Supabase in prod) with automatic SQLite
  fallback for local dev
- **Hosting:** Render (backend) · Vercel (static frontend)

## Game state model

State is **per session**: each WebSocket connection gets its own player row,
created on connect and removed on disconnect — so concurrent players never share
or clobber each other's game. The `locations` map is shared and read-only.

The database backend is chosen by the `DATABASE_URL` env var: set it (to a
Supabase **pooler** connection string) for PostgreSQL; leave it unset for SQLite.

## Getting started

- **Run locally:** see [LOCAL_SETUP.md](LOCAL_SETUP.md) — no PostgreSQL needed
  (SQLite is automatic when `DATABASE_URL` is unset).
- **Deploy:** see [DEPLOYMENT.md](DEPLOYMENT.md) — Render + Vercel + Supabase.

### Quickstart (local)

```bash
# 1. install
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 2. create .env with ANTHROPIC_API_KEY and DEEPGRAM_API_KEY (leave DATABASE_URL unset)

# 3. backend on :8080  (the frontend expects this port locally)
bash start.sh

# 4. frontend on :3001  (separate terminal)
python -m http.server 3001 --directory client
# open http://localhost:3001
```

## Environment variables

| Variable | Required | Notes |
|----------|----------|-------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `DEEPGRAM_API_KEY` | Yes | Deepgram STT key |
| `DATABASE_URL` | Prod only | Supabase **pooler** URI → PostgreSQL; unset → SQLite |
| `VERCEL_FRONTEND_URL` | Prod | Frontend domain, for CORS |
