# Ludex

Ludex helps users choose what to play from their existing Steam library. The project is currently in local development.

## Documentation

- [Project design](PROJECT_DESIGN.md) defines the product problem, scope, user
  journeys, requirements, and product decisions.
- [Technical design](TECHNICAL_DESIGN.md) defines architecture, data and trust
  boundaries, APIs, flows, reliability, and testing strategy.
- [Architecture overview](docs/ARCHITECTURE.md) explains the system boundaries,
  data flows, and links to detailed component notes.
- [Checkpoint journal](docs/CHECKPOINT.md) records completed work, verification,
  and the exact continuation point.
- [Visual design](UI_DESIGN.md) defines the Ludex interface language.

## Local application stack

Ludex runs three services:

| Service  | Technology                  | Local URL             |
| -------- | --------------------------- | --------------------- |
| Frontend | React, TypeScript, and Vite | http://localhost:5173 |
| Backend  | FastAPI and SQLAlchemy      | http://localhost:8000 |
| Database | PostgreSQL 18               | localhost:5432        |

## Prerequisites

To run the complete application:

-  Docker Desktop
-  Docker Compose, included with Docker Desktop

To run tests directly on the host:

-  Python 3.12 or newer
-  `uv`
-  Node.js 24 and npm

## Start the application

First create the ignored backend environment file from its safe example:

```bash
cp backend/.env.example backend/.env
```

Before starting Ludex, replace the placeholder values for `STEAM_API_KEY`,
`IGDB_CLIENT_ID`, and `IGDB_CLIENT_SECRET` in `backend/.env`. These credentials
remain backend-only. Leave `GEMINI_API_KEY` commented out; Gemini is optional and
is not used by the active application.

Then, from the project root, run:

```bash
docker compose up --build
```

Compose will:

1. Start PostgreSQL.
2. Wait for PostgreSQL to become healthy.
3. Apply all Alembic migrations to the database.
4. Start the FastAPI backend only after migrations succeed.
5. Wait for the backend health check to pass.
6. Start the React frontend.

Once startup completes, open:

-  Frontend: http://localhost:5173
-  Backend health endpoint: http://localhost:8000/health
-  Interactive API documentation: http://localhost:8000/docs

The frontend should display:

```text
Backend: connected
```

## First-run data workflow

Open http://localhost:5173. Enter a Steam ID or public Steam profile URL.
When that profile is not already cached, Ludex imports its public Steam library
and creates one browser access session. Returning with that session reads only
the cache. Use **Refresh Steam library** when you explicitly want to contact
Steam and update ownership or playtime.

Preference validation and recommendation requests use cached database facts and
never call Steam, IGDB, Gemini, or another provider. A new Steam import does not
populate IGDB facts. The default command is report-only: it shows aggregate
readiness without provider calls or writes.

```bash
cd backend
uv run python -m app.igdb_enrichment_command
```

After reviewing that report, explicitly enrich the uniquely owned pending games
with the configured backend IGDB credentials:

```bash
uv run python -m app.igdb_enrichment_command --apply
```

Only `--apply` contacts IGDB. It uses the bounded enrichment service, prints
aggregate before/after coverage, and exits nonzero with a sanitized report when
IGDB fails; successful earlier batches remain committed for a safe retry. No
automatic endpoint or background worker exists. Recommendation requests remain
cache-only, and Gemini is neither constructed nor required.

## Verify the installation

With the normal database running, execute the complete provider-free release
verification from the project root:

```bash
./scripts/verify_release_candidate.sh
```

The script validates Compose; runs the complete backend tests, compilation, and
migration checks; runs the frontend tests, lint, and production build; and checks
the working diff for whitespace errors. It does not start or stop containers,
apply IGDB enrichment, contact a provider, or alter volumes.

To run the same gates individually, first validate Compose from the project
root:

```bash
docker compose config --quiet
```

With the database running, verify the backend from `backend/`:

```bash
uv run pytest
uv run python -m compileall app
uv run alembic check
```

The tests replace provider transports and do not consume real Steam, IGDB, or
Gemini quota. `alembic check` compares the models with the running PostgreSQL
schema.

Install and verify the frontend from `frontend/`:

```bash
npm ci
npm test
npm run lint
npm run build
```

The backend health endpoint should return:

```json
{
   "status": "healthy",
   "database": "connected"
}
```

## Back up the database

Choose an existing host directory outside the repository and a new destination
name. The commands below refuse an existing destination before creating a
compressed custom-format PostgreSQL backup:

```bash
ludex_backup_dir="/absolute/path/to/ludex-backups"
mkdir -p "$ludex_backup_dir"
ludex_backup_path="$ludex_backup_dir/ludex-$(date +%Y%m%d-%H%M%S).dump"
test ! -e "$ludex_backup_path"
docker compose exec -T database pg_dump -U ludex -d ludex -Fc > "$ludex_backup_path"
test -s "$ludex_backup_path"
docker run --rm --volume "$ludex_backup_dir:/backups:ro" postgres:18-alpine pg_restore --list "/backups/$(basename "$ludex_backup_path")"
```

Keep backups outside the Docker volume. Listing the archive verifies that it is
readable; it is not a restore test. Practice restoration only into a separate
database. Do not use destructive `pg_restore --clean` options against the only
copy of Ludex data.

## Stop the application

If Compose is running in the foreground, press **Control+C**.

To remove the stopped containers and local network, run:

```bash
docker compose down
```

The PostgreSQL data remains in the `postgres_data` Docker volume.

`docker compose down --volumes` permanently deletes the Compose-managed database
volume. It is not part of normal shutdown. Use it only when you explicitly
intend to erase local Ludex data and have confirmed any needed backup.

## Run profile-retention maintenance

From the `backend` directory, preview profiles eligible for the 30-day cleanup:

```bash
uv run python -m app.retention_cleanup_command
```

Preview is the default and does not change data. After reviewing that report and
confirming a database backup is available, apply exactly the currently eligible
cleanup with the explicit flag:

```bash
uv run python -m app.retention_cleanup_command --apply
```

Application rechecks eligibility in one transaction, removes only eligible
profile, access-session, and profile-ownership rows, and retains shared game and
IGDB facts. This command is manual maintenance; recommendation and session
requests never trigger it.

## Environment variables

The standard Docker Compose workflow supplies local database, origin, and cookie
settings. It reads private Steam and IGDB credentials from the ignored
`backend/.env` created during setup.

Example files document the complete configuration surface:

-  `backend/.env.example`
-  `frontend/.env.example`

The backend example is copied during the standard Compose setup. The frontend
example is needed only when running Vite directly with a local override. Real
`.env` files are excluded from Git and Docker build contexts.

Backend configuration:

-  `DATABASE_URL` specifies the PostgreSQL connection.
-  `FRONTEND_ORIGIN` specifies the browser origin permitted by CORS.
-  `ACCESS_SESSION_COOKIE_SECURE` is `false` only for local HTTP development.
-  `STEAM_API_KEY` enables Steam profile and library imports.
-  `IGDB_CLIENT_ID` and `IGDB_CLIENT_SECRET` enable factual enrichment.
-  `GEMINI_API_KEY` is optional and unused by the active application.

Frontend configuration:

-  `VITE_API_BASE_URL` specifies the backend URL used by browser requests.

Variables prefixed with `VITE_` are included in browser code and must never contain passwords, API keys, or other secrets.

## Local networking

Code running directly on the host reaches PostgreSQL through `localhost`.

The backend container reaches PostgreSQL through the Compose service hostname `database`.

Browser code reaches the backend through `http://localhost:8000`, even when the frontend itself is running in a container.

## Troubleshooting

**Ports 5173, 8000, or 5432 are unavailable:** stop the conflicting local
process, or use the documented `LUDEX_FRONTEND_PORT`, `LUDEX_BACKEND_PORT`, and
`LUDEX_DATABASE_PORT` overrides together with matching `LUDEX_API_BASE_URL` and
`LUDEX_FRONTEND_ORIGIN` values.

**Compose reports that `backend/.env` is missing:** copy
`backend/.env.example` as described above and replace the required Steam and
IGDB placeholders. Do not put secrets in the frontend environment.

**The backend does not become healthy:** inspect `docker compose logs backend`.
The migration must complete before FastAPI starts. Compare `uv run alembic
current` with `uv run alembic heads`; do not bypass a failed migration with
`create_all`, stamping, or deletion of the database volume.

**The health response is unavailable:** inspect `docker compose ps`, then check
database health before backend health. A healthy response has `"status":
"healthy"` and `"database": "connected"`.

**A Steam profile cannot be imported:** confirm that it is a public profile with
a public game library and that the Steam key is valid. A private Steam library
cannot be imported. A failed import or refresh must not erase an existing cache.

To rebuild after dependency or container configuration changes, run:

```bash
docker compose up --build
```
