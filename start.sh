#!/bin/bash
set -e

# Nix-managed Python installs binaries in unpredictable nix-store paths.
# Find the python3 binary's directory and add it to PATH so pip-installed
# tools (alembic, uvicorn) are on PATH.
PYTHON_BIN_DIR=$(dirname "$(which python3)")
export PATH="/root/.local/bin:$HOME/.local/bin:$PYTHON_BIN_DIR:$PATH"

# Diagnostic — visible in deploy logs
echo "PATH: $PATH"
echo "python3: $(which python3 2>&1 || echo 'NOT FOUND')"
echo "alembic: $(which alembic 2>&1 || echo 'NOT FOUND')"
echo "uvicorn: $(which uvicorn 2>&1 || echo 'NOT FOUND')"

# Fail loudly if critical tools missing
if ! command -v alembic &> /dev/null; then
  echo "ERROR: alembic not findable after PATH fix"
  exit 1
fi
if ! command -v uvicorn &> /dev/null; then
  echo "ERROR: uvicorn not findable after PATH fix"
  exit 1
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
