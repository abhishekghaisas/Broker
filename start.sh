#!/bin/bash

# Start MCP server in the background
python mcp_server.py &
MCP_PID=$!

# Start main backend server
gunicorn main:app --workers 2 --worker-class uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT

# Cleanup: kill MCP server when main server stops
kill $MCP_PID
