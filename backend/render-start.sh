#!/bin/sh
set -eu

port="${PORT:-8000}"

exec uv run --no-sync fastapi run app/main.py --host 0.0.0.0 --port "$port"
