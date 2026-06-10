#!/bin/bash
set -e

echo "🚀 Starting MCP server on port 8001..."
python mcp_server.py > /tmp/mcp.log 2>&1 &
MCP_PID=$!
echo "MCP Server PID: $MCP_PID"

sleep 2

echo "🚀 Starting backend server on port $PORT..."
gunicorn main:app \
  --workers 2 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:$PORT \
  --access-logfile - \
  --error-logfile - &

BACKEND_PID=$!
echo "Backend Server PID: $BACKEND_PID"

# Keep services running
wait $BACKEND_PID

# Cleanup
kill $MCP_PID 2>/dev/null || true
