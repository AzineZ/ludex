#!/bin/sh
set -eu

port="${PORT:-8000}"

exec uv run --no-sync uvicorn app.hosted:app \
    --host 0.0.0.0 \
    --port "$port" \
    --no-access-log
