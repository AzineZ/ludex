import stat
import json
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.managed_database_bootstrap import (
    MIGRATION_ROLE_NAME,
    RUNTIME_ROLE_NAME,
    build_role_connection_url,
    run_managed_database_bootstrap,
    validate_admin_connection_urls,
    write_runtime_environment,
)


DIRECT_URL = (
    "postgresql://neondb_owner:admin-secret@"
    "ep-example.us-west-2.aws.neon.tech/neondb"
    "?sslmode=require&channel_binding=require"
)
POOLED_URL = (
    "postgresql://neondb_owner:admin-secret@"
    "ep-example-pooler.us-west-2.aws.neon.tech/neondb"
    "?sslmode=require&channel_binding=require"
)


def test_validates_matching_direct_and_pooled_admin_urls() -> None:
    connections = validate_admin_connection_urls(DIRECT_URL, POOLED_URL)

    assert connections.direct_url == DIRECT_URL
    assert connections.pooled_url == POOLED_URL
    assert connections.database_name == "neondb"


@pytest.mark.parametrize(
    ("direct_url", "pooled_url"),
    [
        (POOLED_URL, POOLED_URL),
        (DIRECT_URL, DIRECT_URL),
        (DIRECT_URL.replace("/neondb", "/other"), POOLED_URL),
        (
            DIRECT_URL.replace("sslmode=require", "sslmode=disable"),
            POOLED_URL,
        ),
    ],
)
def test_rejects_unsafe_or_mismatched_admin_urls(
    direct_url: str,
    pooled_url: str,
) -> None:
    with pytest.raises(ValueError) as error:
        validate_admin_connection_urls(direct_url, pooled_url)

    assert "admin-secret" not in str(error.value)


def test_builds_encoded_sqlalchemy_role_url_without_admin_credentials() -> None:
    role_url = build_role_connection_url(
        POOLED_URL,
        RUNTIME_ROLE_NAME,
        "generated/_password",
    )

    assert role_url.startswith(
        "postgresql+psycopg://ludex_app:generated%2F_password@"
    )
    assert "-pooler." in role_url
    assert "admin-secret" not in role_url


def test_writes_new_runtime_environment_with_owner_only_permissions(
    tmp_path: Path,
) -> None:
    destination = tmp_path / ".env.neon-staging"

    write_runtime_environment(
        destination,
        direct_admin_url=DIRECT_URL,
        pooled_admin_url=POOLED_URL,
        migration_password="migration-secret",
        runtime_password="runtime-secret",
    )

    contents = destination.read_text(encoding="utf-8")
    assert contents.splitlines() == [
        (
            "DATABASE_URL=postgresql+psycopg://ludex_app:runtime-secret@"
            "ep-example-pooler.us-west-2.aws.neon.tech/neondb"
            "?sslmode=require&channel_binding=require"
        ),
        (
            "MIGRATION_DATABASE_URL=postgresql+psycopg://"
            "ludex_migrator:migration-secret@"
            "ep-example.us-west-2.aws.neon.tech/neondb"
            "?sslmode=require&channel_binding=require"
        ),
    ]
    assert "neondb_owner" not in contents
    assert "admin-secret" not in contents
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600


def test_refuses_to_overwrite_an_existing_runtime_environment(
    tmp_path: Path,
) -> None:
    destination = tmp_path / ".env.neon-staging"
    destination.write_text("preserve-me", encoding="utf-8")

    with pytest.raises(FileExistsError):
        write_runtime_environment(
            destination,
            direct_admin_url=DIRECT_URL,
            pooled_admin_url=POOLED_URL,
            migration_password="migration-secret",
            runtime_password="runtime-secret",
        )

    assert destination.read_text(encoding="utf-8") == "preserve-me"


def test_role_names_are_separate_and_non_owner() -> None:
    assert MIGRATION_ROLE_NAME == "ludex_migrator"
    assert RUNTIME_ROLE_NAME == "ludex_app"
    assert MIGRATION_ROLE_NAME != RUNTIME_ROLE_NAME
    assert not MIGRATION_ROLE_NAME.endswith("owner")
    assert not RUNTIME_ROLE_NAME.endswith("owner")


def test_staging_bootstrap_runs_one_guarded_migration_pipeline(
    tmp_path: Path,
) -> None:
    admin_environment = tmp_path / ".env.neon-staging-admin"
    admin_environment.write_text(
        (
            f"NEON_ADMIN_DIRECT_URL={DIRECT_URL}\n"
            f"NEON_ADMIN_POOLED_URL={POOLED_URL}\n"
        ),
        encoding="utf-8",
    )
    admin_environment.chmod(0o600)
    runtime_environment = tmp_path / ".env.neon-staging"
    output = StringIO()
    passwords = iter(["migration-secret", "runtime-secret"])
    role_creator = MagicMock()
    defaults_configurer = MagicMock()
    migration_runner = MagicMock(return_value="d52e7a91c304")
    finalizer = MagicMock(return_value=12)

    exit_code = run_managed_database_bootstrap(
        [
            "--environment",
            "staging",
            "--admin-env-file",
            str(admin_environment),
            "--output-env-file",
            str(runtime_environment),
        ],
        output=output,
        password_factory=lambda: next(passwords),
        role_creator=role_creator,
        defaults_configurer=defaults_configurer,
        migration_runner=migration_runner,
        finalizer=finalizer,
    )

    assert exit_code == 0
    assert json.loads(output.getvalue()) == {
        "alembic_revision": "d52e7a91c304",
        "environment": "staging",
        "public_table_count": 12,
        "status": "ready",
    }
    role_creator.assert_called_once()
    defaults_configurer.assert_called_once()
    migration_runner.assert_called_once()
    finalizer.assert_called_once_with(
        DIRECT_URL,
        (
            "postgresql+psycopg://ludex_migrator:migration-secret@"
            "ep-example.us-west-2.aws.neon.tech/neondb"
            "?sslmode=require&channel_binding=require"
        ),
        (
            "postgresql+psycopg://ludex_app:runtime-secret@"
            "ep-example-pooler.us-west-2.aws.neon.tech/neondb"
            "?sslmode=require&channel_binding=require"
        ),
        "d52e7a91c304",
    )
    assert stat.S_IMODE(runtime_environment.stat().st_mode) == 0o600


def test_production_bootstrap_requires_confirmation_and_backup(
    tmp_path: Path,
) -> None:
    admin_environment = tmp_path / ".env.neon-production-admin"
    admin_environment.write_text(
        (
            f"NEON_ADMIN_DIRECT_URL={DIRECT_URL}\n"
            f"NEON_ADMIN_POOLED_URL={POOLED_URL}\n"
        ),
        encoding="utf-8",
    )
    admin_environment.chmod(0o600)
    output = StringIO()
    role_creator = MagicMock()

    exit_code = run_managed_database_bootstrap(
        [
            "--environment",
            "production",
            "--admin-env-file",
            str(admin_environment),
            "--output-env-file",
            str(tmp_path / ".env.neon-production"),
        ],
        output=output,
        role_creator=role_creator,
    )

    assert exit_code == 2
    assert json.loads(output.getvalue()) == {
        "environment": "production",
        "failure": "production_confirmation_and_backup_required",
        "status": "blocked",
    }
    role_creator.assert_not_called()


def test_production_prepare_only_creates_roles_without_migrating(
    tmp_path: Path,
) -> None:
    admin_environment = tmp_path / ".env.neon-production-admin"
    admin_environment.write_text(
        (
            f"NEON_ADMIN_DIRECT_URL={DIRECT_URL}\n"
            f"NEON_ADMIN_POOLED_URL={POOLED_URL}\n"
        ),
        encoding="utf-8",
    )
    admin_environment.chmod(0o600)
    runtime_environment = tmp_path / ".env.neon-production"
    output = StringIO()
    passwords = iter(["migration-secret", "runtime-secret"])
    role_creator = MagicMock()
    defaults_configurer = MagicMock()
    migration_runner = MagicMock()
    finalizer = MagicMock()

    exit_code = run_managed_database_bootstrap(
        [
            "--environment",
            "production",
            "--admin-env-file",
            str(admin_environment),
            "--output-env-file",
            str(runtime_environment),
            "--confirm-production",
            "--prepare-only",
        ],
        output=output,
        password_factory=lambda: next(passwords),
        role_creator=role_creator,
        defaults_configurer=defaults_configurer,
        migration_runner=migration_runner,
        finalizer=finalizer,
    )

    assert exit_code == 0
    assert json.loads(output.getvalue()) == {
        "environment": "production",
        "status": "roles_ready",
    }
    role_creator.assert_called_once()
    defaults_configurer.assert_called_once()
    migration_runner.assert_not_called()
    finalizer.assert_not_called()


def test_resume_uses_existing_runtime_roles_without_recreating_them(
    tmp_path: Path,
) -> None:
    admin_environment = tmp_path / ".env.neon-staging-admin"
    admin_environment.write_text(
        (
            f"NEON_ADMIN_DIRECT_URL={DIRECT_URL}\n"
            f"NEON_ADMIN_POOLED_URL={POOLED_URL}\n"
        ),
        encoding="utf-8",
    )
    admin_environment.chmod(0o600)
    runtime_environment = tmp_path / ".env.neon-staging"
    write_runtime_environment(
        runtime_environment,
        direct_admin_url=DIRECT_URL,
        pooled_admin_url=POOLED_URL,
        migration_password="migration-secret",
        runtime_password="runtime-secret",
    )
    output = StringIO()
    role_creator = MagicMock()
    defaults_configurer = MagicMock()
    migration_runner = MagicMock(return_value="d52e7a91c304")
    finalizer = MagicMock(return_value=12)

    exit_code = run_managed_database_bootstrap(
        [
            "--environment",
            "staging",
            "--admin-env-file",
            str(admin_environment),
            "--output-env-file",
            str(runtime_environment),
            "--resume",
        ],
        output=output,
        role_creator=role_creator,
        defaults_configurer=defaults_configurer,
        migration_runner=migration_runner,
        finalizer=finalizer,
    )

    assert exit_code == 0
    assert json.loads(output.getvalue())["status"] == "ready"
    role_creator.assert_not_called()
    defaults_configurer.assert_called_once()
    migration_runner.assert_called_once()
    finalizer.assert_called_once()
