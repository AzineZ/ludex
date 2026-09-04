#!/bin/sh

set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH= cd -- "$script_directory/.." && pwd)

cd "$project_root"

docker compose config --quiet

(
    cd backend
    uv run pytest
    uv run python -m compileall app
    uv run alembic current
    uv run alembic check
)

(
    cd frontend
    npm test
    npm run lint
    npm run build
)

git diff --check
