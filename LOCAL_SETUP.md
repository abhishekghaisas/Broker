# Local Development Setup

This guide explains how to run the Broker game locally for development.

## Prerequisites

- Python 3.11+ (3.12+ recommended)
- Git
- Anthropic API key
- Deepgram API key
- Node.js (optional, for frontend development only)

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

```bash
# Copy the example file
cp .env.example .env

# Edit .env and add your API keys
# You only need these two for local development:
ANTHROPIC_API_KEY=sk-ant-...
DEEPGRAM_API_KEY=...

# Leave DATABASE_URL blank (uses SQLite automatically)
```

## Step 3: Run the Backend

The backend consists of two services:

### Option A: Run Both Together (Recommended)

```bash
bash start.sh
```

This runs:
- **MCP Server** on `http://localhost:8001`
- **FastAPI Backend** on `http://localhost:8000`

### Option B: Run Services Separately

**Terminal 1 - MCP Server:**
```bash
python mcp_server.py
```

**Terminal 2 - Backend Server:**
```bash
python main.py
```

Or with gunicorn on port 8080:
```bash
gunicorn main:app --workers 1 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:8080
```

## Step 4: Run the Frontend

**Terminal 3 - Frontend (Static Server):**
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
- Uses **PostgreSQL** (Supabase)
- Configured via `DATABASE_URL` environment variable
- Persistent across service restarts

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

- **Hot Reload**: Changes to Python files auto-reload with `python main.py`
- **Frontend Changes**: Just refresh browser, no restart needed
- **Clear Logs**: Use `> /dev/null 2>&1` to suppress logs
- **Debug Mode**: Set `RENDER=false` in `.env` for better error messages

## Next Steps

When ready to deploy:
1. Set up Supabase PostgreSQL (see DEPLOYMENT.md)
2. Deploy backend to Render
3. Deploy frontend to Vercel
4. Add `DATABASE_URL` to Render environment

See [DEPLOYMENT.md](DEPLOYMENT.md) for full production setup.
