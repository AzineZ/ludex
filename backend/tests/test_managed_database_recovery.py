from pathlib import Path

from app.managed_database_recovery import postgres_environment


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DIRECT_URL = (
    "postgresql+psycopg://ludex_migrator:encoded%2Fsecret@"
    "ep-example.us-west-2.aws.neon.tech/neondb"
    "?sslmode=require&channel_binding=require"
)


def test_builds_pg_environment_without_putting_secrets_in_arguments() -> None:
    environment = postgres_environment(DIRECT_URL)

    assert environment == {
        "PGCHANNELBINDING": "require",
        "PGDATABASE": "neondb",
        "PGHOST": "ep-example.us-west-2.aws.neon.tech",
        "PGPASSWORD": "encoded/secret",
        "PGPORT": "5432",
        "PGSSLMODE": "require",
        "PGUSER": "ludex_migrator",
    }


def test_managed_rehearsal_is_bounded_and_non_destructive() -> None:
    source = (PROJECT_ROOT / "backend/app/managed_database_recovery.py").read_text(
        encoding="utf-8"
    )

    assert "tempfile.mkdtemp" in source
    assert 'recovery_database = f"ludex_recovery_' in source
    assert 'sql.SQL("CREATE DATABASE {}")' in source
    assert '"GRANT USAGE, CREATE ON SCHEMA public TO {}"' in source
    assert '"DROP DATABASE IF EXISTS {} WITH (FORCE)"' in source
    assert '"pg_dump"' in source
    assert '"--format=custom"' in source
    assert '"pg_restore"' in source
    assert '"--list"' in source
    assert '"--exit-on-error"' in source
    assert '"--no-owner"' in source
    assert '"--no-privileges"' in source
    assert '"--no-comments"' in source
    assert "--clean" not in source
    assert '"alembic", "check"' in source
    assert "shutil.rmtree(working_directory)" in source


def test_managed_rehearsal_uses_staging_credentials_only() -> None:
    source = (PROJECT_ROOT / "backend/app/managed_database_recovery.py").read_text(
        encoding="utf-8"
    )

    assert 'choices=("staging",)' in source
    assert "_load_admin_connections" in source
    assert "MIGRATION_DATABASE_URL" in source
    assert ".env.neon-production" not in source
