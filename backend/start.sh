#!/bin/sh
set -eu

port="${PORT:-8000}"

uv run alembic upgrade head
exec uv run fastapi run app/main.py --host 0.0.0.0 --port "$port"
