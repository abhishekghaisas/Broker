#!/bin/bash

echo "🚀 Booting up the Tri-Terminal Broker Architecture..."

# Capture the absolute path of your project directory
PROJECT_DIR=$(pwd)

# 1. Boot Terminal 1: The Lore Boundary (New Window)
echo "🛡️ Opening new terminal for Lore Boundary (mcp_server.py)..."
osascript -e "tell application \"Terminal\" to do script \"cd '$PROJECT_DIR' && source .venv/bin/activate && python mcp_server.py\""

sleep 2 # Brief pause to allow the SSE network bindings to establish


# 3. Boot Terminal 3: The Main Router (Current Window)
echo "🧠 Booting Main Event Broker (main.py) on port 8000..."
source .venv/bin/activate
python main.py