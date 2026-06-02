#!/bin/bash
set -e

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
