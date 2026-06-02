#!/bin/bash
set -e

# pip install --break-system-packages puts binaries here in the Nixpacks runtime.
# Add both common locations to PATH so alembic/uvicorn are findable.
export PATH="/root/.local/bin:$HOME/.local/bin:$PATH"

# Diagnostic: confirm tools are findable before we try to use them.
echo "PATH: $PATH"
echo "alembic: $(which alembic 2>&1 || echo 'NOT FOUND')"
echo "uvicorn: $(which uvicorn 2>&1 || echo 'NOT FOUND')"

# If alembic still isn't on PATH, find it the hard way and put it there.
if ! command -v alembic &> /dev/null; then
  echo "alembic not on PATH; searching..."
  ALEMBIC_PATH=$(find / -name "alembic" -type f -executable 2>/dev/null | grep -v proc | head -1)
  if [ -n "$ALEMBIC_PATH" ]; then
    ALEMBIC_DIR=$(dirname "$ALEMBIC_PATH")
    export PATH="$ALEMBIC_DIR:$PATH"
    echo "Found alembic at $ALEMBIC_PATH, added $ALEMBIC_DIR to PATH"
  else
    echo "ERROR: alembic not found anywhere in container. Build install step did not produce expected binaries."
    exit 1
  fi
fi

echo "Running database migrations..."
cd /app/backend && alembic upgrade head
cd /app

echo "Starting FastAPI on port 8000..."
cd /app/backend && uvicorn app.main:app --host 127.0.0.1 --port 8000 &
FASTAPI_PID=$!

sleep 3

if ! kill -0 $FASTAPI_PID 2>/dev/null; then
  echo "FastAPI failed to start. Exiting."
  exit 1
fi

echo "Starting Next.js on port $PORT..."
cd /app/frontend && npm start
