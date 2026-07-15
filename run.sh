#!/bin/bash
set -e
cd "$(dirname "$0")"

# Build frontend if needed
if [ ! -d "frontend/dist" ]; then
    echo "Building frontend..."
    cd frontend && npm install && npm run build && cd ..
fi

# Ensure data directory
mkdir -p data/sessions

# Start server
echo "Starting Motion Chat at http://localhost:8000"
python3 -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --log-level info
