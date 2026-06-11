import modal
import os

# Create Modal app
app = modal.App("broker-backend")

# Mount the current directory so all project files are available
mount = modal.Mount.from_local_dir(".", remote_path="/root")

@app.function(
    mounts=[mount],
    secrets=[
        modal.Secret.from_name("broker-secrets")  # Contains ANTHROPIC_API_KEY, DEEPGRAM_API_KEY, DATABASE_URL
    ],
    allow_concurrent_requests=True,
)
@modal.asgi_app()
def fastapi_app():
    """ASGI app for Broker backend."""
    from main import app as fastapi_app
    return fastapi_app
