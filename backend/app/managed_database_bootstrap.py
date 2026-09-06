"""Safe helpers for bootstrapping isolated managed PostgreSQL databases."""

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from typing import Callable, TextIO
from urllib.parse import parse_qs, quote, unquote, urlsplit, urlunsplit

from alembic.config import Config
from alembic.script import ScriptDirectory
from dotenv import dotenv_values
import psycopg
from psycopg import sql


MIGRATION_ROLE_NAME = "ludex_migrator"
RUNTIME_ROLE_NAME = "ludex_app"
_POSTGRESQL_SCHEMES = {
    "postgres",
    "postgresql",
    "postgresql+psycopg",
}
_BACKEND_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class AdminConnectionUrls:
    """Validated direct and pooled owner connections for one database."""

    direct_url: str
    pooled_url: str
    database_name: str


@dataclass(frozen=True)
class RoleConnectionUrls:
    """Validated direct migrator and pooled application connections."""

    migration_url: str
    runtime_url: str


def _validated_url_parts(url: str):
    parts = urlsplit(url)
    query = parse_qs(parts.query)

    if (
        parts.scheme not in _POSTGRESQL_SCHEMES
        or not parts.hostname
        or not parts.username
        or parts.password is None
        or not parts.path.lstrip("/")
        or "/" in parts.path.lstrip("/")
        or query.get("sslmode") != ["require"]
        or query.get("channel_binding") != ["require"]
    ):
        raise ValueError("The managed database connection is invalid or unsafe.")

    return parts


def validate_admin_connection_urls(
    direct_url: str,
    pooled_url: str,
) -> AdminConnectionUrls:
    """Validate one matching TLS-only direct/pooler credential pair."""
    direct = _validated_url_parts(direct_url)
    pooled = _validated_url_parts(pooled_url)
    direct_hostname = direct.hostname or ""
    pooled_hostname = pooled.hostname or ""

    if (
        "-pooler." in direct_hostname
        or "-pooler." not in pooled_hostname
        or pooled_hostname.replace("-pooler.", ".", 1) != direct_hostname
        or direct.username != pooled.username
        or direct.path != pooled.path
        or direct.port != pooled.port
    ):
        raise ValueError(
            "The direct and pooled managed database connections do not match."
        )

    return AdminConnectionUrls(
        direct_url=direct_url,
        pooled_url=pooled_url,
        database_name=direct.path.lstrip("/"),
    )


def build_role_connection_url(
    admin_url: str,
    role_name: str,
    password: str,
) -> str:
    """Replace owner credentials and select SQLAlchemy's psycopg dialect."""
    parts = _validated_url_parts(admin_url)
    hostname = parts.hostname
    if hostname is None:
        raise ValueError("The managed database hostname is missing.")

    host = f"[{hostname}]" if ":" in hostname else hostname
    if parts.port is not None:
        host = f"{host}:{parts.port}"
    netloc = (
        f"{quote(role_name, safe='')}:{quote(password, safe='')}@{host}"
    )

    return urlunsplit(
        (
            "postgresql+psycopg",
            netloc,
            parts.path,
            parts.query,
            "",
        )
    )


def write_runtime_environment(
    destination: Path,
    *,
    direct_admin_url: str,
    pooled_admin_url: str,
    migration_password: str,
    runtime_password: str,
) -> None:
    """Create, without overwriting, one owner-readable runtime secret file."""
    connections = validate_admin_connection_urls(
        direct_admin_url,
        pooled_admin_url,
    )
    runtime_url = build_role_connection_url(
        connections.pooled_url,
        RUNTIME_ROLE_NAME,
        runtime_password,
    )
    migration_url = build_role_connection_url(
        connections.direct_url,
        MIGRATION_ROLE_NAME,
        migration_password,
    )
    contents = (
        f"DATABASE_URL={runtime_url}\n"
        f"MIGRATION_DATABASE_URL={migration_url}\n"
    )
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL,
        0o600,
    )

    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(contents)
    except BaseException:
        destination.unlink(missing_ok=True)
        raise


def _to_psycopg_url(url: str) -> str:
    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def _load_admin_connections(path: Path) -> AdminConnectionUrls:
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError(
            "The admin environment must exist with owner-only permissions."
        )

    values = dotenv_values(path)
    direct_url = values.get("NEON_ADMIN_DIRECT_URL")
    pooled_url = values.get("NEON_ADMIN_POOLED_URL")
    if not isinstance(direct_url, str) or not isinstance(pooled_url, str):
        raise ValueError("The admin environment is incomplete.")

    return validate_admin_connection_urls(direct_url, pooled_url)


def _load_role_connections(
    path: Path,
    admin_connections: AdminConnectionUrls,
) -> RoleConnectionUrls:
    if not path.is_file() or path.stat().st_mode & 0o077:
        raise ValueError(
            "The runtime environment must exist with owner-only permissions."
        )

    values = dotenv_values(path)
    migration_url = values.get("MIGRATION_DATABASE_URL")
    runtime_url = values.get("DATABASE_URL")
    if not isinstance(migration_url, str) or not isinstance(runtime_url, str):
        raise ValueError("The runtime environment is incomplete.")

    migration = _validated_url_parts(migration_url)
    runtime = _validated_url_parts(runtime_url)
    admin_direct = _validated_url_parts(admin_connections.direct_url)
    admin_pooled = _validated_url_parts(admin_connections.pooled_url)
    if (
        unquote(migration.username or "") != MIGRATION_ROLE_NAME
        or unquote(runtime.username or "") != RUNTIME_ROLE_NAME
        or migration.hostname != admin_direct.hostname
        or runtime.hostname != admin_pooled.hostname
        or migration.port != admin_direct.port
        or runtime.port != admin_pooled.port
        or migration.path != admin_direct.path
        or runtime.path != admin_pooled.path
        or migration.query != admin_direct.query
        or runtime.query != admin_pooled.query
    ):
        raise ValueError("The runtime connections do not match this database.")

    return RoleConnectionUrls(
        migration_url=migration_url,
        runtime_url=runtime_url,
    )


def create_least_privilege_roles(
    admin_direct_url: str,
    database_name: str,
    migration_password: str,
    runtime_password: str,
    *,
    require_empty: bool = False,
) -> None:
    """Create separate non-owner migration and application login roles."""
    with psycopg.connect(_to_psycopg_url(admin_direct_url)) as connection:
        if connection.info.dbname != database_name:
            raise RuntimeError("The connected database does not match.")

        with connection.cursor() as cursor:
            if require_empty:
                cursor.execute(
                    "SELECT count(*) FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
                if cursor.fetchone()[0] != 0:
                    raise RuntimeError(
                        "Role preparation requires an empty database."
                    )

            cursor.execute(
                "SELECT rolname FROM pg_roles WHERE rolname = ANY(%s)",
                ([MIGRATION_ROLE_NAME, RUNTIME_ROLE_NAME],),
            )
            if cursor.fetchall():
                raise RuntimeError("A managed Ludex role already exists.")

            role_options = sql.SQL(
                " LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE "
                "NOREPLICATION"
            )
            cursor.execute(
                sql.SQL("CREATE ROLE {}{}").format(
                    sql.Identifier(MIGRATION_ROLE_NAME),
                    role_options.format(sql.Literal(migration_password)),
                )
            )
            cursor.execute(
                sql.SQL("CREATE ROLE {}{}").format(
                    sql.Identifier(RUNTIME_ROLE_NAME),
                    role_options.format(sql.Literal(runtime_password)),
                )
            )
            cursor.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}, {}").format(
                    sql.Identifier(database_name),
                    sql.Identifier(MIGRATION_ROLE_NAME),
                    sql.Identifier(RUNTIME_ROLE_NAME),
                )
            )
            cursor.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
            cursor.execute(
                sql.SQL("GRANT USAGE, CREATE ON SCHEMA public TO {}").format(
                    sql.Identifier(MIGRATION_ROLE_NAME)
                )
            )
            cursor.execute(
                sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(
                    sql.Identifier(RUNTIME_ROLE_NAME)
                )
            )


def configure_migrator_defaults(migration_url: str) -> None:
    """Make future migrator-owned application objects usable by the app role."""
    with psycopg.connect(_to_psycopg_url(migration_url)) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                    "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
                ).format(sql.Identifier(RUNTIME_ROLE_NAME))
            )
            cursor.execute(
                sql.SQL(
                    "ALTER DEFAULT PRIVILEGES IN SCHEMA public "
                    "GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO {}"
                ).format(sql.Identifier(RUNTIME_ROLE_NAME))
            )


def run_alembic_migrations(migration_url: str) -> str:
    """Upgrade and compare one database through its direct migration URL."""
    environment = os.environ.copy()
    environment["DATABASE_URL"] = migration_url
    environment["MIGRATION_DATABASE_URL"] = migration_url

    for arguments in (("upgrade", "head"), ("current",), ("check",)):
        subprocess.run(
            [sys.executable, "-m", "alembic", *arguments],
            cwd=_BACKEND_ROOT,
            env=environment,
            check=True,
        )

    alembic_config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    heads = ScriptDirectory.from_config(alembic_config).get_heads()
    if len(heads) != 1:
        raise RuntimeError("The migration history does not have one head.")

    return heads[0]


def finalize_and_verify_database(
    admin_direct_url: str,
    migration_url: str,
    runtime_url: str,
    expected_revision: str,
) -> int:
    """Remove app access to Alembic state and verify least privilege."""
    # Default privileges were established by the migrator role, so that role
    # must also revoke its grant on Alembic's internal state table. The Neon
    # owner role is intentionally not relied upon as a PostgreSQL superuser.
    with psycopg.connect(_to_psycopg_url(migration_url)) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                sql.SQL(
                    "REVOKE ALL PRIVILEGES ON TABLE public.alembic_version "
                    "FROM {}"
                ).format(sql.Identifier(RUNTIME_ROLE_NAME))
            )

    with psycopg.connect(_to_psycopg_url(admin_direct_url)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT version_num FROM public.alembic_version")
            revision_row = cursor.fetchone()
            if revision_row is None or revision_row[0] != expected_revision:
                raise RuntimeError("The applied Alembic revision is unexpected.")

            cursor.execute(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'public'"
            )
            table_count = cursor.fetchone()[0]
            cursor.execute(
                "SELECT bool_and(tableowner = %s) FROM pg_tables "
                "WHERE schemaname = 'public'",
                (MIGRATION_ROLE_NAME,),
            )
            tables_owned_by_migrator = cursor.fetchone()[0]
            cursor.execute(
                "SELECT has_schema_privilege(%s, 'public', 'USAGE'), "
                "NOT has_schema_privilege(%s, 'public', 'CREATE'), "
                "has_table_privilege(%s, 'public.profiles', 'SELECT'), "
                "has_table_privilege(%s, 'public.profiles', 'INSERT'), "
                "has_table_privilege(%s, 'public.profiles', 'UPDATE'), "
                "has_table_privilege(%s, 'public.profiles', 'DELETE'), "
                "NOT has_table_privilege("
                "%s, 'public.alembic_version', 'SELECT')",
                (
                    RUNTIME_ROLE_NAME,
                    RUNTIME_ROLE_NAME,
                    RUNTIME_ROLE_NAME,
                    RUNTIME_ROLE_NAME,
                    RUNTIME_ROLE_NAME,
                    RUNTIME_ROLE_NAME,
                    RUNTIME_ROLE_NAME,
                ),
            )
            privilege_checks = cursor.fetchone()
            cursor.execute(
                "SELECT bool_and("
                "NOT rolsuper AND NOT rolcreatedb AND NOT rolcreaterole "
                "AND NOT rolreplication) "
                "FROM pg_roles WHERE rolname = ANY(%s)",
                ([MIGRATION_ROLE_NAME, RUNTIME_ROLE_NAME],),
            )
            safe_role_attributes = cursor.fetchone()[0]

    if (
        not table_count
        or not tables_owned_by_migrator
        or not all(privilege_checks)
        or not safe_role_attributes
    ):
        raise RuntimeError("The least-privilege database verification failed.")

    with psycopg.connect(_to_psycopg_url(runtime_url)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT count(*) FROM public.profiles")
            if cursor.fetchone()[0] != 0:
                raise RuntimeError("The fresh database unexpectedly has profiles.")

    return table_count


def _generate_password() -> str:
    return secrets.token_urlsafe(32)


def _write_result(output: TextIO, result: dict[str, object]) -> None:
    output.write(json.dumps(result, sort_keys=True))
    output.write("\n")


def run_managed_database_bootstrap(
    arguments: list[str],
    *,
    output: TextIO = sys.stdout,
    password_factory: Callable[[], str] = _generate_password,
    role_creator: Callable[..., None] = create_least_privilege_roles,
    defaults_configurer: Callable[..., None] = configure_migrator_defaults,
    migration_runner: Callable[..., str] = run_alembic_migrations,
    finalizer: Callable[..., int] = finalize_and_verify_database,
) -> int:
    """Bootstrap one isolated database without exposing generated secrets."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--environment",
        choices=("staging", "production"),
        required=True,
    )
    parser.add_argument("--admin-env-file", type=Path, required=True)
    parser.add_argument("--output-env-file", type=Path, required=True)
    parser.add_argument("--confirm-production", action="store_true")
    parser.add_argument("--prechange-backup", type=Path)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--prepare-only", action="store_true")
    action.add_argument("--resume", action="store_true")
    options = parser.parse_args(arguments)

    production_backup_missing = (
        not options.prepare_only
        and (
            options.prechange_backup is None
            or not options.prechange_backup.is_file()
            or options.prechange_backup.stat().st_size == 0
        )
    )
    if options.environment == "production" and (
        not options.confirm_production or production_backup_missing
    ):
        _write_result(
            output,
            {
                "environment": "production",
                "failure": "production_confirmation_and_backup_required",
                "status": "blocked",
            },
        )
        return 2

    output_environment = options.output_env_file
    if not output_environment.name.startswith(".env.neon-"):
        _write_result(
            output,
            {
                "environment": options.environment,
                "failure": "unsafe_output_filename",
                "status": "blocked",
            },
        )
        return 2

    stage = "load_admin_environment"
    environment_written = False
    roles_created = False
    try:
        connections = _load_admin_connections(options.admin_env_file)
        if options.resume:
            stage = "load_runtime_environment"
            role_connections = _load_role_connections(
                output_environment,
                connections,
            )
            migration_url = role_connections.migration_url
            runtime_url = role_connections.runtime_url
            roles_created = True
        else:
            migration_password = password_factory()
            runtime_password = password_factory()
            migration_url = build_role_connection_url(
                connections.direct_url,
                MIGRATION_ROLE_NAME,
                migration_password,
            )
            runtime_url = build_role_connection_url(
                connections.pooled_url,
                RUNTIME_ROLE_NAME,
                runtime_password,
            )

            stage = "write_runtime_environment"
            write_runtime_environment(
                output_environment,
                direct_admin_url=connections.direct_url,
                pooled_admin_url=connections.pooled_url,
                migration_password=migration_password,
                runtime_password=runtime_password,
            )
            environment_written = True

            stage = "create_roles"
            role_creator(
                connections.direct_url,
                connections.database_name,
                migration_password,
                runtime_password,
                require_empty=(
                    options.environment == "production"
                    and options.prepare_only
                ),
            )
            roles_created = True

        stage = "configure_default_privileges"
        defaults_configurer(migration_url)
        if options.prepare_only:
            _write_result(
                output,
                {
                    "environment": options.environment,
                    "status": "roles_ready",
                },
            )
            return 0

        stage = "run_migrations"
        revision = migration_runner(migration_url)
        stage = "finalize_and_verify"
        table_count = finalizer(
            connections.direct_url,
            migration_url,
            runtime_url,
            revision,
        )
    except Exception:
        if environment_written and not roles_created:
            output_environment.unlink(missing_ok=True)
        _write_result(
            output,
            {
                "environment": options.environment,
                "failure": stage,
                "status": "failed",
            },
        )
        return 1

    _write_result(
        output,
        {
            "alembic_revision": revision,
            "environment": options.environment,
            "public_table_count": table_count,
            "status": "ready",
        },
    )
    return 0


def main() -> None:
    raise SystemExit(run_managed_database_bootstrap(sys.argv[1:]))


if __name__ == "__main__":
    main()
