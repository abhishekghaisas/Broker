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

1. Go to [render.com](https://render.com) and sign in
2. Click **"New +"** → **"Web Service"**
3. Connect your GitHub repository
4. Configure the service:
   - **Name**: `broker-backend`
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: Leave empty (uses Procfile)
   - **Instance Type**: Free or Starter (depending on your needs)

### 1.2 Set Environment Variables

In the Render dashboard for your service:

1. Go to **"Environment"** tab
2. Add the following environment variables:
   ```
   ANTHROPIC_API_KEY=<your-api-key>
   DEEPGRAM_API_KEY=<your-api-key>
   VERCEL_FRONTEND_URL=<your-vercel-domain>.vercel.app
   ```

### 1.3 Deploy

- Click **"Create Web Service"**
- Render will automatically deploy when you push to GitHub
- Note your service URL (e.g., `https://broker-backend.onrender.com`)

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

### 2.3 Set Environment Variables

In the Vercel dashboard for your project:

1. Go to **"Settings"** → **"Environment Variables"**
2. Add:
   ```
   REACT_APP_BACKEND_URL=https://broker-backend.onrender.com
   ```

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

If you're using a custom Render domain, you can pass it to the frontend in two ways:

### Option A: Via Vercel Environment Variable (Recommended)

1. In Vercel settings, add: `REACT_APP_BACKEND_URL=https://your-render-url.onrender.com`
2. Redeploy

### Option B: Via Window Variable

Add a `<script>` tag in `client/index.html` before `app.js`:

```html
<script>
    window.BROKER_BACKEND_URL = 'https://your-render-url.onrender.com';
</script>
```

## Step 4: Test the Deployment

1. Open your Vercel URL in a browser
2. Click "INITIATE OPERATION" to see the main menu
3. Click "Connect Audio" and test the game flow
4. Verify:
   - WebSocket connection to backend works
   - Game state updates work
   - Audio playback works (if microphone is accessible)

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
| `DEEPGRAM_API_KEY` | Yes | Deepgram API key |
| `VERCEL_FRONTEND_URL` | Yes | Vercel frontend domain (for CORS) |
| `PORT` | No | Server port (default: 8000) |
| `RENDER` | No | Set automatically by Render |

### Frontend (Vercel)
| Variable | Required | Description |
|----------|----------|-------------|
| `REACT_APP_BACKEND_URL` | No | Backend API URL (auto-detected if not set) |

## Troubleshooting

### WebSocket Connection Fails
- Ensure backend CORS includes your Vercel domain
- Check that `VERCEL_FRONTEND_URL` is set correctly in Render

### API Errors
- Verify `ANTHROPIC_API_KEY` and `DEEPGRAM_API_KEY` are set in Render
- Check Render logs for detailed error messages

### Game State Not Updating
- Ensure `/state` endpoint is responding: `curl https://broker-backend.onrender.com/state`
- Check browser console for fetch errors

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

The game uses SQLite (`game_state.db`). On Render's free tier, this file may be reset when the service restarts. For production with persistent data, consider upgrading to a PostgreSQL database.

## Support

For deployment issues:
- **Render**: Check logs in Render Dashboard → Your Service → "Logs"
- **Vercel**: Check logs in Vercel Dashboard → Your Project → "Deployments"
- **API Keys**: Ensure your API key limits haven't been exceeded
