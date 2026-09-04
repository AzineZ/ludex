#!/bin/sh
set -eu

uv run alembic upgrade head
exec uv run fastapi run app/main.py --host 0.0.0.0 --port 8000
