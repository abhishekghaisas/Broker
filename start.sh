#!/bin/bash
set -e

# Set default port (8080 for local dev, 8000 for production via environment)
PORT=${PORT:-8080}

echo "🚀 Starting backend server on port $PORT..."
gunicorn main:app \
  --workers 1 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:$PORT \
  --access-logfile - \
  --error-logfile -
