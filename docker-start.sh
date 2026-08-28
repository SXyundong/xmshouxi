#!/bin/sh
set -eu

cd /app/backend
alembic upgrade head
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
backend_pid=$!

cd /app/frontend
PORT="${PORT:-3000}" npm run start -- --hostname 0.0.0.0 &
frontend_pid=$!

shutdown() {
  kill "$backend_pid" "$frontend_pid" 2>/dev/null || true
}

trap shutdown INT TERM EXIT

while kill -0 "$backend_pid" 2>/dev/null && kill -0 "$frontend_pid" 2>/dev/null; do
  sleep 2
done

echo "A web process exited unexpectedly; stopping the container." >&2
exit 1
