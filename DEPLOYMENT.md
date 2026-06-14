# Deployment Guide: Broker

This guide explains how to deploy the Broker game to production using **Render** (backend) and **Vercel** (frontend).

## Prerequisites

1. **Render account** - https://render.com
2. **Vercel account** - https://vercel.com
3. **GitHub repository** - Code pushed to GitHub (Render and Vercel integrate via GitHub)
4. **API Keys**:
   - `ANTHROPIC_API_KEY` - From Anthropic
   - `DEEPGRAM_API_KEY` - From Deepgram

## Step 1: Deploy Backend to Render

### 1.1 Create a Render Service

#### Option A: Using render.yaml (Recommended)

1. Go to [render.com](https://render.com) and sign in
2. Click **"New +"** → **"Web Service"** → **"Public Git Repository"**
3. Enter your GitHub repo URL
4. Render will automatically detect `render.yaml` and configure everything

#### Option B: Manual Configuration via Dashboard

1. Go to [render.com](https://render.com) and sign in
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository
4. Configure the service:
   - **Name**: `broker-backend`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `gunicorn main:app --workers 1 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT`
   - **Instance Type**: Free or Starter (depending on your needs)

### 1.2 Set Environment Variables

In the Render dashboard for your service:

1. Go to **"Environment"** tab
2. Add the following environment variables:
   ```
   ANTHROPIC_API_KEY=<your-api-key>
   DEEPGRAM_API_KEY=<your-api-key>
   VERCEL_FRONTEND_URL=<your-vercel-domain>.vercel.app
   DATABASE_URL=<your-supabase-pooler-connection-string>
   ```
   See [**Step 1.5: Database (Supabase PostgreSQL)**](#15-database-supabase-postgresql)
   below for exactly which Supabase connection string to use.

### 1.3 Deploy

- Click **"Create Web Service"**
- Render will automatically deploy when you push to GitHub
- Note your service URL (e.g., `https://broker-backend.onrender.com`)

### 1.5 Database (Supabase PostgreSQL)

Production persists game state in PostgreSQL via the `psycopg` (v3) driver
(already in `requirements.txt`). The backend reads `DATABASE_URL`:

- **If `DATABASE_URL` is set** → PostgreSQL.
- **If unset** → SQLite (`game_state.db`), which is **ephemeral** on Render's
  free tier and wiped on every restart. Set `DATABASE_URL` for real persistence.

**Use the Supabase connection POOLER URI** — Supabase → Project → **Connect** →
"Connection string". There are three options; pick correctly:

| Option | Host / Port | Works from Render free tier? |
|---|---|---|
| Direct connection | `db.<ref>.supabase.co:5432` | ❌ IPv6-only on the free tier — Render free web services are IPv4-only and cannot reach it |
| **Transaction pooler** | `...pooler.supabase.com:6543` | ✅ Recommended |
| Session pooler | `...pooler.supabase.com:5432` | ✅ Also works |

Notes:
- The app sets `prepare_threshold=None` so it works under the pooler's
  transaction mode (no "prepared statement already exists" errors).
- Paste the **raw** password into the URL — the app percent-encodes credentials
  automatically, so a password containing `@` won't corrupt host parsing. (If
  the password also contains `/`, `?`, or `#`, resetting it to an alphanumeric
  one in Supabase is the simplest fix.)
- The `players` table is **per session** (one row per live connection, created on
  connect and removed on disconnect); only the shared `locations` map is seeded.

## Step 2: Deploy Frontend to Vercel

### 2.1 Prepare Frontend

The frontend is in the `client/` folder. Before deploying, you may want to update the default backend URL in `client/app.js` if not using the default Render URL.

### 2.2 Create a Vercel Project

1. Go to [vercel.com](https://vercel.com) and sign in
2. Click **"Add New"** → **"Project"**
3. Import your GitHub repository
4. Configure the project:
   - **Framework**: `Other` (static site)
   - **Root Directory**: `client`
   - **Build Command**: Leave empty or `echo "Static site"`
   - **Output Directory**: `.`

### 2.3 Point the Frontend at Your Backend

The client is a **static site** (no build step), so it does not read env vars at
build time. `client/app.js` chooses the backend URL at runtime:

- On a `*.vercel.app` host it uses `window.BROKER_BACKEND_URL` if defined,
  otherwise the hard-coded default Render URL in `app.js`.
- On localhost it uses `http://localhost:8080`.

To target your own Render backend, do **one** of:

- **Edit the default** in `client/app.js` (the `https://broker-...onrender.com`
  fallback), or
- **Set `window.BROKER_BACKEND_URL`** via a `<script>` tag in
  `client/index.html` before `app.js` (see [Step 3](#step-3-update-backend-url-in-frontend)).

### 2.4 Deploy

- Click **"Deploy"**
- Vercel will deploy your frontend from the `client/` folder
- Note your Vercel URL (e.g., `https://broker.vercel.app`)

### 2.5 Update Backend CORS (if needed)

If your Vercel domain is different from what's in the environment variable:

1. Go back to Render dashboard
2. Update `VERCEL_FRONTEND_URL` to match your actual Vercel domain
3. Redeploy the backend

## Step 3: Update Backend URL in Frontend

If you're using a custom Render domain, point the frontend at it in one of two ways:

### Option A: Window Variable (Recommended)

Add a `<script>` tag in `client/index.html` before `app.js`:

```html
<script>
    window.BROKER_BACKEND_URL = 'https://your-render-url.onrender.com';
</script>
```

### Option B: Edit the Default

Change the hard-coded fallback URL in `client/app.js` (the
`https://broker-...onrender.com` value in the `BACKEND_URL` resolver).

## Step 4: Test the Deployment

1. Open your Vercel URL in a browser
2. Click "INITIATE OPERATION" to see the main menu
3. Click "Connect Audio" and test the game flow
4. Verify:
   - WebSocket connection to backend works
   - Game state (HUD) updates work
   - NOVA speaks back (via the browser's built-in speech synthesis)
   - The Render logs show `✅ Database initialized successfully (PostgreSQL).`

## Step 5: Custom Domain (Optional)

### For Render Backend
1. Go to **Render Dashboard** → Your Service → **"Settings"**
2. Under **"Custom Domain"**, add your domain
3. Follow the DNS configuration steps

### For Vercel Frontend
1. Go to **Vercel Dashboard** → Your Project → **"Settings"** → **"Domains"**
2. Add your custom domain
3. Update DNS records as instructed

## Environment Variables Reference

### Backend (Render)
| Variable | Required | Description |
|----------|----------|-------------|
| `ANTHROPIC_API_KEY` | Yes | Claude API key |
| `DEEPGRAM_API_KEY` | Yes | Deepgram API key (STT) |
| `VERCEL_FRONTEND_URL` | Yes | Vercel frontend domain (for CORS) |
| `DATABASE_URL` | Recommended | Supabase **pooler** connection string. Unset → ephemeral SQLite |
| `PORT` | No | Server port (set automatically by Render) |
| `RENDER` | No | Set automatically by Render |

### Frontend (Vercel)
The static client takes no build-time env vars. Set the backend URL at runtime
via `window.BROKER_BACKEND_URL` or the default in `client/app.js` (see Step 3).

## Troubleshooting

### WebSocket Connection Fails
- Ensure backend CORS includes your Vercel domain
- Check that `VERCEL_FRONTEND_URL` is set correctly in Render

### API Errors
- Verify `ANTHROPIC_API_KEY` and `DEEPGRAM_API_KEY` are set in Render
- Check Render logs for detailed error messages

### Game State Not Updating
- Health-check the service: `curl https://broker-backend.onrender.com/`
  (the `/state` endpoint now requires a `?sid=<session>` and returns 400 without one)
- Check browser console for fetch errors

### Database Connection Fails
- `failed to resolve host 'db.<ref>.supabase.co'` → you used the **direct**
  connection; switch `DATABASE_URL` to the Supabase **pooler** URI (see Step 1.5)
- Logs show `(SQLite)` instead of `(PostgreSQL)` → `DATABASE_URL` is not set on Render
- `prepared statement already exists` → ensure you're on the current code
  (it disables prepared statements for the pooler)

### Microphone/Audio Issues
- May be restricted on free Render instances due to resource limits
- Consider upgrading to a Starter instance if needed

## Local Development

To continue local development while backend is deployed:

```bash
# Update client/app.js to point to deployed backend
# Or set it in browser console:
window.BROKER_BACKEND_URL = 'https://your-render-url.onrender.com';

# Then run frontend locally:
python -m http.server 3000 --directory client
```

## Database Note

The backend supports both PostgreSQL and SQLite, selected automatically by the
`DATABASE_URL` environment variable (see [Step 1.5](#15-database-supabase-postgresql)):

- **Production** → set `DATABASE_URL` to your Supabase **pooler** connection
  string for persistent PostgreSQL state.
- **Local dev / `DATABASE_URL` unset** → SQLite (`game_state.db`). On Render's
  free tier this file is ephemeral and reset on every restart, so always set
  `DATABASE_URL` in production.

Game state is per session (one player row per live connection), so concurrent
players are isolated from one another.

## Support

For deployment issues:
- **Render**: Check logs in Render Dashboard → Your Service → "Logs"
- **Vercel**: Check logs in Vercel Dashboard → Your Project → "Deployments"
- **API Keys**: Ensure your API key limits haven't been exceeded
-----------------------------