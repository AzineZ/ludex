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

From the project root, run:

```bash
docker compose up --build
```

Compose will:

1. Start PostgreSQL.
2. Wait for PostgreSQL to become healthy.
3. Start the FastAPI backend.
4. Wait for the backend health check to pass.
5. Start the React frontend.

Once startup completes, open:

-  Frontend: http://localhost:5173
-  Backend health endpoint: http://localhost:8000/health
-  Interactive API documentation: http://localhost:8000/docs

The frontend should display:

```text
Backend: connected
```

## Stop the application

If Compose is running in the foreground, press **Control+C**.

To remove the stopped containers and local network, run:

```bash
docker compose down
```

The PostgreSQL data remains in the `postgres_data` Docker volume.

Do not add `--volumes` unless you intentionally want to delete the local database data.

## Run backend tests

From the `backend` directory, run:

```bash
uv run pytest
```

The health-endpoint test uses a controlled database-session replacement and does not require a running PostgreSQL instance.

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

## Run frontend checks

Install the locked frontend dependencies:

```bash
cd frontend
npm ci
```

Run the component tests:

```bash
npm test
```

Run linting:

```bash
npm run lint
```

Verify the production build:

```bash
npm run build
```

## Environment variables

The standard Docker Compose workflow supplies the required environment variables automatically.

Example files are provided for running services directly on the host:

-  `backend/.env.example`
-  `frontend/.env.example`

Copy an example to `.env` only when you need local overrides. Real `.env` files are excluded from Git and Docker build contexts.

Backend configuration:

-  `DATABASE_URL` specifies the PostgreSQL connection.
-  `FRONTEND_ORIGIN` specifies the browser origin permitted by CORS.

Frontend configuration:

-  `VITE_API_BASE_URL` specifies the backend URL used by browser requests.

Variables prefixed with `VITE_` are included in browser code and must never contain passwords, API keys, or other secrets.

## Local networking

Code running directly on the host reaches PostgreSQL through `localhost`.

The backend container reaches PostgreSQL through the Compose service hostname `database`.

Browser code reaches the backend through `http://localhost:8000`, even when the frontend itself is running in a container.

## Troubleshooting

If a service cannot start, check whether ports `5173`, `8000`, or `5432` are already in use.

To rebuild after dependency or container configuration changes, run:

```bash
docker compose up --build
```

The backend health endpoint should return:

```json
{
   "status": "healthy",
   "database": "connected"
}
```
