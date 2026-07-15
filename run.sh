#!/bin/bash
set -e
cd "$(dirname "$0")"

# Load .env if present
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
    echo "Loaded .env configuration"
fi

# Check required env var
if [ -z "$MOTION_LLM_KEY" ]; then
    echo "ERROR: MOTION_LLM_KEY is not set."
    echo "  Copy .env.example to .env and fill in your API key."
    echo "  This is a SEPARATE key from Claude Code — use your own DeepSeek API key."
    exit 1
fi

# Build frontend if needed
if [ ! -d "frontend/dist" ]; then
    echo "Building frontend..."
    cd frontend && npm install && npm run build && cd ..
fi

# Ensure data directory
mkdir -p data/sessions

# Start server
echo "Starting Motion Chat at http://localhost:8000"
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port "${PORT:-8000}" --log-level info
