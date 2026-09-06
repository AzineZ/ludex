#!/bin/sh

set -eu

script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(CDPATH= cd -- "$script_directory/.." && pwd)
database_port="${LUDEX_DATABASE_PORT:-5432}"

case "$database_port" in
    "" | *[!0-9]*)
        printf '%s\n' "LUDEX_DATABASE_PORT must be numeric." >&2
        exit 2
        ;;
esac

rehearsal_prefix="ludex_rehearsal_$(date -u +%Y%m%d%H%M%S)_$$"
source_database="${rehearsal_prefix}_source"
restore_database="${rehearsal_prefix}_restore"
working_directory=$(mktemp -d "${TMPDIR:-/tmp}/ludex-recovery.XXXXXX")
archive_path="$working_directory/rehearsal.dump"

cleanup() {
    cd "$project_root"
    docker compose exec -T database \
        dropdb --if-exists -U ludex "$restore_database" \
        >/dev/null 2>&1 || true
    docker compose exec -T database \
        dropdb --if-exists -U ludex "$source_database" \
        >/dev/null 2>&1 || true
    rm -f -- "$archive_path"
    rmdir "$working_directory" 2>/dev/null || true
}

trap cleanup EXIT

database_url() {
    printf '%s' \
        "postgresql+psycopg://ludex:ludex@localhost:${database_port}/$1"
}

verify_database() {
    rehearsal_database_url=$(database_url "$1")

    (
        cd "$project_root/backend"
        MIGRATION_DATABASE_URL="$rehearsal_database_url" \
            uv run alembic current
        MIGRATION_DATABASE_URL="$rehearsal_database_url" \
            uv run alembic check
    )
}

cd "$project_root"
docker compose exec -T database pg_isready -U ludex -d ludex
docker compose exec -T database createdb -U ludex "$source_database"

source_database_url=$(database_url "$source_database")
(
    cd "$project_root/backend"
    MIGRATION_DATABASE_URL="$source_database_url" \
        uv run alembic upgrade head
)
verify_database "$source_database"

test ! -e "$archive_path"
docker compose exec -T database \
    pg_dump -U ludex -d "$source_database" -Fc >"$archive_path"
test -s "$archive_path"
docker compose exec -T database pg_restore --list <"$archive_path" >/dev/null

docker compose exec -T database createdb -U ludex "$restore_database"
docker compose exec -T database \
    pg_restore --exit-on-error -U ludex -d "$restore_database" \
    <"$archive_path"
verify_database "$restore_database"

source_revision=$(
    docker compose exec -T database \
        psql -U ludex -d "$source_database" -At \
        -c "SELECT version_num FROM alembic_version"
)
restore_revision=$(
    docker compose exec -T database \
        psql -U ludex -d "$restore_database" -At \
        -c "SELECT version_num FROM alembic_version"
)
source_table_count=$(
    docker compose exec -T database \
        psql -U ludex -d "$source_database" -At \
        -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
)
restore_table_count=$(
    docker compose exec -T database \
        psql -U ludex -d "$restore_database" -At \
        -c "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'public'"
)

test "$source_revision" = "d52e7a91c304"
test "$restore_revision" = "$source_revision"
test "$source_table_count" -gt 0
test "$restore_table_count" = "$source_table_count"

archive_bytes=$(wc -c <"$archive_path" | tr -d ' ')
archive_checksum=$(shasum -a 256 "$archive_path" | awk '{print $1}')

printf '%s\n' \
    "Fresh migration and separate-database restore rehearsal passed." \
    "Alembic revision: $restore_revision" \
    "Public tables: $restore_table_count" \
    "Archive bytes: $archive_bytes" \
    "Archive SHA-256: $archive_checksum"
