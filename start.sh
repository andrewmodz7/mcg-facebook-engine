#!/bin/bash
set -e

# Apply migrations against the live DB before serving any traffic.
echo "Running database migrations..."
cd /app/backend && /opt/venv/bin/alembic upgrade head
cd /app

# Start FastAPI on port 8000 in the background (internal only)
echo "Starting FastAPI on port 8000..."
cd /app/backend && /opt/venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000 &
FASTAPI_PID=$!

# Give FastAPI 3 seconds to start before launching Next.js
sleep 3

# If FastAPI died on startup, fail loudly
if ! kill -0 $FASTAPI_PID 2>/dev/null; then
  echo "FastAPI failed to start. Exiting."
  exit 1
fi

# Start Next.js on the Railway-assigned port (foreground)
echo "Starting Next.js on port $PORT..."
cd /app/frontend && npm start
