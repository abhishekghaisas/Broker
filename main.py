from dotenv import load_dotenv
load_dotenv()

import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from broker.router import router as broker_router

#Initialize non-blocking Python backend
app = FastAPI(title="Broker")

# CORS configuration for local dev and production
allowed_origins = [
    "http://localhost:3000",
    "http://localhost:8000",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:8000",
]

# Add Vercel frontend domain if set via environment variable
vercel_domain = os.getenv("VERCEL_FRONTEND_URL")
if vercel_domain:
    allowed_origins.append(f"https://{vercel_domain}")
    allowed_origins.append(f"http://{vercel_domain}")

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#Mount modularized broker router
app.include_router(broker_router)

if __name__ == "__main__":
    #Run broker locally (port from env or default to 8000)
    port = int(os.getenv("PORT", 8000))
    host = "0.0.0.0" if os.getenv("RENDER") else "127.0.0.1"
    reload = not os.getenv("RENDER")  # Disable reload in production

    uvicorn.run("main:app", host=host, port=port, reload=reload)