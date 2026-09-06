#!/bin/sh
set -eu

port="${PORT:-8000}"

exec uv run --no-sync fastapi run app/hosted.py --host 0.0.0.0 --port "$port"
