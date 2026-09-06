"""Rehearse a managed staging backup and restore without touching its source."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import quote, unquote, urlsplit, urlunsplit

from dotenv import dotenv_values
import psycopg
from psycopg import sql

from app.managed_database_bootstrap import (
    MIGRATION_ROLE_NAME,
    RUNTIME_ROLE_NAME,
    _load_admin_connections,
    _to_psycopg_url,
    _validated_url_parts,
)


POSTGRES_IMAGE = "postgres:18-alpine"
EXPECTED_REVISION = "6a2f8e4c91bd"
_BACKEND_ROOT = Path(__file__).resolve().parents[1]


class ManagedRecoveryError(RuntimeError):
    """Report only a safe rehearsal stage while retaining the private cause."""

    def __init__(self, stage: str) -> None:
        super().__init__(f"Managed recovery rehearsal failed at {stage}.")
        self.stage = stage


def postgres_environment(url: str) -> dict[str, str]:
    """Translate a validated URL into libpq variables kept out of argv."""
    parts = _validated_url_parts(url)
    if parts.hostname is None or parts.username is None or parts.password is None:
        raise ValueError("The managed database connection is incomplete.")

    return {
        "PGCHANNELBINDING": "require",
        "PGDATABASE": parts.path.lstrip("/"),
        "PGHOST": parts.hostname,
        "PGPASSWORD": unquote(parts.password),
        "PGPORT": str(parts.port or 5432),
        "PGSSLMODE": "require",
        "PGUSER": unquote(parts.username),
    }


def _replace_database(url: str, database_name: str) -> str:
    parts = _validated_url_parts(url)
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            f"/{quote(database_name, safe='')}",
            parts.query,
            "",
        )
    )


def _load_migration_url(path: Path, admin_direct_url: str) -> str:
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError(
            "The runtime environment must exist with owner-only permissions."
        )

    value = dotenv_values(path).get("MIGRATION_DATABASE_URL")
    if not isinstance(value, str):
        raise ValueError("The runtime environment is incomplete.")

    migration = _validated_url_parts(value)
    admin = _validated_url_parts(admin_direct_url)
    if (
        unquote(migration.username or "") != MIGRATION_ROLE_NAME
        or migration.hostname != admin.hostname
        or migration.port != admin.port
        or migration.path != admin.path
        or migration.query != admin.query
        or "-pooler." in (migration.hostname or "")
    ):
        raise ValueError("The migration connection does not match staging.")

    return value


def _run_postgres_tool(
    arguments: list[str],
    *,
    connection_url: str,
    working_directory: Path,
) -> None:
    environment = os.environ.copy()
    environment.update(postgres_environment(connection_url))
    command = [
        "docker",
        "run",
        "--rm",
        "--volume",
        f"{working_directory}:/backup",
    ]
    for variable in sorted(postgres_environment(connection_url)):
        command.extend(("--env", variable))
    command.extend((POSTGRES_IMAGE, *arguments))
    subprocess.run(
        command,
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _database_facts(connection_url: str) -> tuple[str, int]:
    with psycopg.connect(_to_psycopg_url(connection_url)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version_num FROM public.alembic_version")
            revision = cursor.fetchone()
            cursor.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
            table_count = cursor.fetchone()

    if revision is None or table_count is None:
        raise RuntimeError("The managed database facts are incomplete.")
    return revision[0], table_count[0]


def _run_alembic_check(connection_url: str) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = connection_url
    environment["MIGRATION_DATABASE_URL"] = connection_url
    subprocess.run(
        [sys.executable, "-m", "alembic", "check"],
        cwd=_BACKEND_ROOT,
        env=environment,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as archive:
        for block in iter(lambda: archive.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _configure_recovered_privileges(
    admin_url: str,
    migration_url: str,
) -> None:
    """Reapply reviewed role grants instead of trusting archived ACLs."""
    with psycopg.connect(_to_psycopg_url(admin_url)) as connection:
        connection.execute(
            sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                sql.Identifier(RUNTIME_ROLE_NAME)
            )
        )

    with psycopg.connect(_to_psycopg_url(migration_url)) as connection:
        connection.execute(
            sql.SQL(
                "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES "
                "IN SCHEMA public TO {}"
            ).format(sql.Identifier(RUNTIME_ROLE_NAME))
        )
        connection.execute(
            sql.SQL(
                "GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES "
                "IN SCHEMA public TO {}"
            ).format(sql.Identifier(RUNTIME_ROLE_NAME))
        )
        connection.execute(
            sql.SQL(
                "REVOKE ALL PRIVILEGES ON TABLE public.alembic_version "
                "FROM {}"
            ).format(sql.Identifier(RUNTIME_ROLE_NAME))
        )


def rehearse_managed_database_recovery(
    admin_environment: Path,
    runtime_environment: Path,
) -> dict[str, object]:
    """Restore staging into a generated database, verify it, then remove it."""
    connections = _load_admin_connections(admin_environment)
    migration_url = _load_migration_url(
        runtime_environment,
        connections.direct_url,
    )
    recovery_database = f"ludex_recovery_{secrets.token_hex(6)}"
    working_directory = Path(tempfile.mkdtemp(prefix="ludex-managed-recovery-"))
    archive_path = working_directory / "rehearsal.dump"
    recovery_created = False
    stage = "inspect_staging_source"

    try:
        source_revision, source_table_count = _database_facts(migration_url)
        if source_revision != EXPECTED_REVISION or source_table_count <= 0:
            raise RuntimeError("The staging source is not at the expected head.")

        stage = "create_backup_archive"
        _run_postgres_tool(
            ["pg_dump", "--format=custom", "--file=/backup/rehearsal.dump"],
            connection_url=migration_url,
            working_directory=working_directory,
        )
        if not archive_path.is_file() or archive_path.stat().st_size == 0:
            raise RuntimeError("The managed backup archive is empty.")
        archive_path.chmod(0o600)
        stage = "inspect_backup_archive"
        _run_postgres_tool(
            ["pg_restore", "--list", "/backup/rehearsal.dump"],
            connection_url=migration_url,
            working_directory=working_directory,
        )

        stage = "create_recovery_database"
        with psycopg.connect(
            _to_psycopg_url(connections.direct_url),
            autocommit=True,
        ) as connection:
            connection.execute(
                sql.SQL("CREATE DATABASE {}").format(
                    sql.Identifier(recovery_database)
                )
            )
        recovery_created = True

        recovery_admin_url = _replace_database(
            connections.direct_url,
            recovery_database,
        )
        with psycopg.connect(_to_psycopg_url(recovery_admin_url)) as connection:
            connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            connection.execute(
                sql.SQL(
                    "GRANT USAGE, CREATE ON SCHEMA public TO {}"
                ).format(sql.Identifier(MIGRATION_ROLE_NAME))
            )

        recovery_migration_url = _replace_database(
            migration_url,
            recovery_database,
        )
        stage = "restore_backup_archive"
        _run_postgres_tool(
            [
                "pg_restore",
                "--exit-on-error",
                "--no-owner",
                "--no-privileges",
                "--no-comments",
                "--dbname",
                recovery_database,
                "/backup/rehearsal.dump",
            ],
            connection_url=recovery_migration_url,
            working_directory=working_directory,
        )
        _configure_recovered_privileges(
            recovery_admin_url,
            recovery_migration_url,
        )
        stage = "verify_restored_schema"
        _run_alembic_check(recovery_migration_url)
        recovery_revision, recovery_table_count = _database_facts(
            recovery_migration_url
        )
        if (
            recovery_revision != source_revision
            or recovery_table_count != source_table_count
        ):
            raise RuntimeError("The managed recovery facts do not match staging.")

        return {
            "alembic_revision": recovery_revision,
            "archive_bytes": archive_path.stat().st_size,
            "archive_sha256": _sha256_file(archive_path),
            "environment": "staging",
            "public_table_count": recovery_table_count,
            "status": "recovery_rehearsal_passed",
        }
    except Exception as error:
        raise ManagedRecoveryError(stage) from error
    finally:
        try:
            if recovery_created:
                with psycopg.connect(
                    _to_psycopg_url(connections.direct_url),
                    autocommit=True,
                ) as connection:
                    connection.execute(
                        sql.SQL(
                            "DROP DATABASE IF EXISTS {} WITH (FORCE)"
                        ).format(sql.Identifier(recovery_database))
                    )
        finally:
            shutil.rmtree(working_directory)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", choices=("staging",), required=True)
    parser.add_argument("--admin-env-file", type=Path, required=True)
    parser.add_argument("--runtime-env-file", type=Path, required=True)
    options = parser.parse_args()

    try:
        result = rehearse_managed_database_recovery(
            options.admin_env_file,
            options.runtime_env_file,
        )
    except ManagedRecoveryError as error:
        result = {
            "environment": "staging",
            "failure": error.stage,
            "status": "recovery_rehearsal_failed",
        }
        if isinstance(error.__cause__, psycopg.Error):
            result["database_error_code"] = error.__cause__.sqlstate or "unknown"
        print(json.dumps(result, sort_keys=True))
        raise SystemExit(1)
    except Exception:
        print(
            json.dumps(
                {
                    "environment": "staging",
                    "failure": "validate_inputs",
                    "status": "recovery_rehearsal_failed",
                },
                sort_keys=True,
            )
        )
        raise SystemExit(1)

    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
