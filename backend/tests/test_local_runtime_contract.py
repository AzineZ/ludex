from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_project_file(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def active_environment_keys(example: str) -> set[str]:
    return {
        line.split("=", maxsplit=1)[0]
        for line in example.splitlines()
        if line and not line.startswith("#") and "=" in line
    }


def test_setup_guide_creates_backend_environment_before_compose_start() -> None:
    readme = read_project_file("README.md")

    copy_position = readme.index("cp backend/.env.example backend/.env")
    start_position = readme.index("docker compose up --build")

    assert copy_position < start_position
    assert "STEAM_API_KEY" in readme[copy_position:start_position]
    assert "IGDB_CLIENT_ID" in readme[copy_position:start_position]
    assert "IGDB_CLIENT_SECRET" in readme[copy_position:start_position]


def test_backend_environment_example_leaves_gemini_disabled() -> None:
    example = read_project_file("backend/.env.example")
    keys = active_environment_keys(example)

    assert "STEAM_API_KEY" in keys
    assert "IGDB_CLIENT_ID" in keys
    assert "IGDB_CLIENT_SECRET" in keys
    assert "GEMINI_API_KEY" not in keys


def test_backend_container_runs_migrations_before_starting_api() -> None:
    dockerfile = read_project_file("backend/Dockerfile")
    startup = read_project_file("backend/start.sh")

    assert 'COPY start.sh ./' in dockerfile
    assert 'CMD ["./start.sh"]' in dockerfile
    migration_position = startup.index("uv run alembic upgrade head")
    api_position = startup.index("uv run fastapi run")

    assert migration_position < api_position


def test_backend_container_stops_when_migration_fails() -> None:
    startup = read_project_file("backend/start.sh")

    assert "set -eu" in startup
    assert "exec uv run fastapi run" in startup


def test_compose_ports_are_overrideable_without_changing_local_defaults() -> None:
    compose = read_project_file("compose.yaml")

    assert '"${LUDEX_DATABASE_PORT:-5432}:5432"' in compose
    assert '"${LUDEX_BACKEND_PORT:-8000}:8000"' in compose
    assert '"${LUDEX_FRONTEND_PORT:-5173}:5173"' in compose
    assert (
        "VITE_API_BASE_URL: "
        "${LUDEX_API_BASE_URL:-http://localhost:8000}"
    ) in compose
    assert (
        "FRONTEND_ORIGIN: "
        "${LUDEX_FRONTEND_ORIGIN:-http://localhost:5173}"
    ) in compose


def test_setup_guide_documents_the_supported_data_workflow() -> None:
    readme = read_project_file("README.md")
    normalized_readme = " ".join(readme.split())

    assert "## First-run data workflow" in readme
    assert "Enter a Steam ID or public Steam profile URL" in normalized_readme
    assert "Refresh Steam library" in normalized_readme
    assert (
        "no supported provider-applying enrichment command, endpoint, or "
        "background worker"
        in normalized_readme
    )
    assert "existing factual IGDB cache" in normalized_readme


def test_setup_guide_lists_complete_verification_commands() -> None:
    readme = read_project_file("README.md")

    assert "## Verify the installation" in readme
    assert "uv run pytest" in readme
    assert "uv run python -m compileall app" in readme
    assert "uv run alembic check" in readme
    assert "npm test" in readme
    assert "npm run lint" in readme
    assert "npm run build" in readme
    assert "docker compose config --quiet" in readme


def test_setup_guide_documents_safe_backup_and_shutdown() -> None:
    readme = read_project_file("README.md")

    assert "## Back up the database" in readme
    assert "test ! -e" in readme
    assert "pg_dump -U ludex -d ludex -Fc" in readme
    assert "pg_restore --list" in readme
    assert "docker compose down" in readme
    assert "docker compose down --volumes" in readme
    assert "permanently deletes" in readme


def test_setup_guide_troubleshoots_runtime_boundaries() -> None:
    readme = read_project_file("README.md")

    assert "Ports 5173, 8000, or 5432" in readme
    assert "migration" in readme
    assert '"status": "healthy"' in readme
    assert "private Steam library" in readme
