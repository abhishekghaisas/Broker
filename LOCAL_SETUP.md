# Local Development Setup

This guide explains how to run the Broker game locally for development.

## Prerequisites

- Python 3.11+ (3.12–3.14 all supported)
- Git
- Anthropic API key
- Deepgram API key

> Local development uses SQLite automatically, so you do **not** need PostgreSQL
> or the `psycopg` driver to run locally — just leave `DATABASE_URL` unset.

## Step 1: Clone and Setup Python Environment

```bash
git clone https://github.com/abhishekghaisas/Broker.git
cd Broker

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate
# On Windows:
venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Step 2: Configure Environment Variables

Create a `.env` file in the project root with your API keys:

```bash
ANTHROPIC_API_KEY=sk-ant-...
DEEPGRAM_API_KEY=...

# Do NOT set DATABASE_URL locally — leaving it unset makes the app use SQLite.
```

For local development you only need the two API keys above.

## Step 3: Run the Backend

The backend is a single FastAPI app (`main.py`). The game logic in
`mcp_server.py` is an imported module, not a separate service.

> **Important:** the frontend looks for the backend at `http://localhost:8080`
> in local development, so run the backend on port **8080**.

### Option A: Use the start script (Recommended)

```bash
bash start.sh
```

`start.sh` launches gunicorn on port 8080 (it honors `$PORT`, defaulting to 8080).

### Option B: Run directly

```bash
gunicorn main:app --workers 1 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8080
```

Or, with auto-reload for development (note: set the port to 8080):

```bash
PORT=8080 python main.py
```

## Step 4: Run the Frontend

In a separate terminal, serve the static client:

```bash
python -m http.server 3001 --directory client
```

Open browser: `http://localhost:3001`

## Step 5: Test the Game

1. Open `http://localhost:3001` in browser
2. Click **"INITIATE OPERATION"** to start
3. Click **"Connect Audio"** to begin
4. Speak naturally to play

## Database

### Local Development
- Uses **SQLite** (`game_state.db`)
- Automatically created on first run
- Data persists between restarts
- No setup needed

### Production (Render)
- Uses **PostgreSQL** (Supabase) via the `psycopg` (v3) driver
- Enabled by setting the `DATABASE_URL` environment variable
- Must be the Supabase **connection pooler** URI (`...pooler.supabase.com`),
  not the direct `db.<ref>.supabase.co` host — see DEPLOYMENT.md
- Game state is **per session**: each browser connection gets its own player
  row, created on connect and removed on disconnect, so players never collide

## Environment Variables Reference

| Variable | Required | Local | Production | Default |
|----------|----------|-------|-----------|---------|
| `ANTHROPIC_API_KEY` | Yes | ✅ | ✅ | - |
| `DEEPGRAM_API_KEY` | Yes | ✅ | ✅ | - |
| `DATABASE_URL` | No | ❌ | ✅ | SQLite |
| `PORT` | No | ❌ | ✅ | 8000 |
| `VERCEL_FRONTEND_URL` | No | ❌ | ✅ | - |

## Troubleshooting

### Port Already in Use
```bash
# Kill process using port 8000
lsof -ti:8000 | xargs kill -9

# Kill process using port 3000
lsof -ti:3000 | xargs kill -9
```

### Microphone Issues
- Check browser permissions (Settings → Privacy)
- Ensure microphone is connected
- Grant permission when prompted

### Database Errors
- Delete `game_state.db` to reset
- Or manually run: `python -c "from mcp_server import init_db; init_db()"`

### API Key Errors
- Verify keys are correct in `.env`
- Check API key limits haven't been exceeded
- Ensure keys are valid

## Development Tips

- **Hot Reload**: `PORT=8080 python main.py` auto-reloads on Python file changes
- **Frontend Changes**: Just refresh browser, no restart needed
- **Reset the game DB**: delete `game_state.db`, or run
  `python -c "from mcp_server import init_db; init_db()"`

## Next Steps

When ready to deploy:
1. Set up Supabase PostgreSQL (see DEPLOYMENT.md)
2. Deploy backend to Render
3. Deploy frontend to Vercel
4. Add `DATABASE_URL` to Render environment

See [DEPLOYMENT.md](DEPLOYMENT.md) for full production setup.
