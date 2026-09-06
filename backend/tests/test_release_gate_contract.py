from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RELEASE_GATE = PROJECT_ROOT / "scripts" / "verify_release_candidate.sh"


def test_release_gate_runs_complete_provider_free_verification() -> None:
    script = RELEASE_GATE.read_text()

    assert "set -eu" in script
    assert "docker compose config --quiet" in script
    assert "uv run pytest" in script
    assert "uv run python -m compileall app" in script
    assert "uv run alembic current" in script
    assert "uv run alembic check" in script
    assert "npm test" in script
    assert "npm run lint" in script
    assert "VITE_API_BASE_URL=/api npm run build" in script
    assert "git diff --check" in script


def test_release_gate_cannot_apply_providers_or_mutate_runtime() -> None:
    script = RELEASE_GATE.read_text()

    assert "igdb_enrichment_command --apply" not in script
    assert "docker compose up" not in script
    assert "docker compose down" not in script
    assert "docker volume" not in script
    assert "curl " not in script


def test_readme_exposes_one_release_verification_command() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text()

    assert "./scripts/verify_release_candidate.sh" in readme
