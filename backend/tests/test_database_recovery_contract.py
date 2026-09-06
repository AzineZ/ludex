from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_project_file(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def test_migration_history_is_one_linear_chain() -> None:
    alembic_config = Config(str(PROJECT_ROOT / "backend" / "alembic.ini"))
    migration_history = ScriptDirectory.from_config(alembic_config)

    assert migration_history.get_heads() == ["6a2f8e4c91bd"]
    assert migration_history.get_bases() == ["cfafdeae2044"]
    assert [
        revision.revision
        for revision in migration_history.walk_revisions(base="base", head="heads")
    ] == [
        "6a2f8e4c91bd",
        "d52e7a91c304",
        "12154eb07460",
        "482cd8b4ee1b",
        "a239bf0112b9",
        "cfafdeae2044",
    ]


def test_local_recovery_rehearsal_uses_only_generated_databases() -> None:
    rehearsal = read_project_file("scripts/rehearse_database_recovery.sh")

    assert "set -eu" in rehearsal
    assert "mktemp -d" in rehearsal
    assert "ludex_rehearsal_" in rehearsal
    assert 'source_database="${rehearsal_prefix}_source"' in rehearsal
    assert 'restore_database="${rehearsal_prefix}_restore"' in rehearsal
    assert "createdb" in rehearsal
    assert "dropdb" in rehearsal
    assert "--if-exists" in rehearsal
    assert "MIGRATION_DATABASE_URL" in rehearsal


def test_local_recovery_rehearsal_verifies_backup_and_restored_schema() -> None:
    rehearsal = read_project_file("scripts/rehearse_database_recovery.sh")

    assert "uv run alembic upgrade head" in rehearsal
    assert "uv run alembic current" in rehearsal
    assert "uv run alembic check" in rehearsal
    assert "pg_dump" in rehearsal
    assert "-Fc" in rehearsal
    assert "pg_restore --list" in rehearsal
    assert "pg_restore --exit-on-error" in rehearsal
    assert "alembic_version" in rehearsal
    assert "information_schema.tables" in rehearsal
    assert "--clean" not in rehearsal
