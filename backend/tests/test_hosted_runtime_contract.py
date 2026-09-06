from pathlib import Path
from typing import Any

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def read_project_file(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def load_blueprint() -> dict[str, Any]:
    blueprint = yaml.safe_load(read_project_file("render.yaml"))

    assert isinstance(blueprint, dict)
    return blueprint


def load_staging_blueprint() -> dict[str, Any]:
    blueprint = yaml.safe_load(
        read_project_file("render.staging-combined.yaml")
    )

    assert isinstance(blueprint, dict)
    return blueprint


def service_named(blueprint: dict[str, Any], name: str) -> dict[str, Any]:
    services = blueprint.get("services")

    assert isinstance(services, list)
    return next(service for service in services if service["name"] == name)


def environment_by_key(service: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["key"]: entry for entry in service["envVars"]}


def test_render_image_builds_frontend_and_backend_for_one_origin() -> None:
    dockerfile = read_project_file("Dockerfile.render")

    assert "FROM node:24-slim AS frontend-builder" in dockerfile
    assert "ENV VITE_API_BASE_URL=/api" in dockerfile
    assert "RUN npm run build" in dockerfile
    assert "FROM python:3.12-slim" in dockerfile
    assert "COPY backend/app ./app" in dockerfile
    assert (
        "COPY --from=frontend-builder /frontend/dist ./frontend-dist"
        in dockerfile
    )


def test_render_blueprint_uses_one_paid_oregon_app_and_shallow_probe() -> None:
    blueprint = load_blueprint()
    backend = service_named(blueprint, "ludex")

    assert len(blueprint["services"]) == 1
    assert backend["type"] == "web"
    assert backend["runtime"] == "docker"
    assert "rootDir" not in backend
    assert backend["dockerfilePath"] == "./Dockerfile.render"
    assert backend["dockerCommand"] == "./render-combined-start.sh"
    assert backend["plan"] == "0.5c-512mb"
    assert backend["region"] == "oregon"
    assert backend["numInstances"] == 1
    assert backend["healthCheckPath"] == "/live"
    assert backend["autoDeployTrigger"] == "off"


def test_render_blueprint_separates_public_values_and_runtime_secrets() -> None:
    backend = service_named(load_blueprint(), "ludex")
    environment = environment_by_key(backend)

    assert environment["FRONTEND_ORIGIN"] == {
        "key": "FRONTEND_ORIGIN",
        "value": "https://ludex.onrender.com",
    }
    assert environment["ACCESS_SESSION_COOKIE_SECURE"] == {
        "key": "ACCESS_SESSION_COOKIE_SECURE",
        "value": "true",
    }
    assert environment["DEPLOYMENT_ENVIRONMENT"] == {
        "key": "DEPLOYMENT_ENVIRONMENT",
        "value": "production",
    }
    assert environment["STEAM_RATE_LIMIT_HMAC_KEY"] == {
        "key": "STEAM_RATE_LIMIT_HMAC_KEY",
        "generateValue": True,
    }
    for key in (
        "DATABASE_URL",
        "STEAM_API_KEY",
        "IGDB_CLIENT_ID",
        "IGDB_CLIENT_SECRET",
    ):
        assert environment[key] == {"key": key, "sync": False}

    assert "GEMINI_API_KEY" not in environment


def test_staging_blueprint_is_free_isolated_and_manual() -> None:
    blueprint = load_staging_blueprint()
    backend = service_named(blueprint, "ludex-staging-app")

    assert len(blueprint["services"]) == 1
    assert backend["runtime"] == "docker"
    assert backend["dockerfilePath"] == "./Dockerfile.render"
    assert backend["dockerCommand"] == "./render-combined-start.sh"
    assert backend["plan"] == "free"
    assert backend["region"] == "oregon"
    assert backend["numInstances"] == 1
    assert backend["healthCheckPath"] == "/live"
    assert backend["autoDeployTrigger"] == "off"


def test_failed_two_service_staging_blueprint_is_marked_obsolete() -> None:
    legacy_blueprint = read_project_file("render.staging.yaml")

    assert legacy_blueprint.startswith("# OBSOLETE:")
    assert "Do not create or manually sync" in legacy_blueprint


def test_staging_blueprint_uses_staging_only_secrets_and_origin() -> None:
    backend = service_named(load_staging_blueprint(), "ludex-staging-app")
    environment = environment_by_key(backend)

    assert environment["FRONTEND_ORIGIN"]["value"] == (
        "https://ludex-staging-app.onrender.com"
    )
    assert environment["DEPLOYMENT_ENVIRONMENT"]["value"] == "staging"
    assert environment["STEAM_RATE_LIMIT_HMAC_KEY"]["generateValue"] is True
    assert environment["DATABASE_URL"] == {
        "key": "DATABASE_URL",
        "sync": False,
    }
    assert "MIGRATION_DATABASE_URL" not in environment
    assert "GEMINI_API_KEY" not in environment


def test_render_start_does_not_run_migrations_in_web_worker() -> None:
    startup = read_project_file("backend/render-combined-start.sh")

    assert "set -eu" in startup
    assert 'port="${PORT:-8000}"' in startup
    assert '--port "$port"' in startup
    assert "app/hosted.py" in startup
    assert "alembic" not in startup


def test_alembic_uses_the_operator_connection_boundary() -> None:
    migration_environment = read_project_file("backend/migrations/env.py")
    backend_example = read_project_file("backend/.env.example")

    assert migration_environment.count("settings.alembic_database_url") == 2
    assert "# MIGRATION_DATABASE_URL=" in backend_example
    assert "direct connection" in backend_example


def test_docker_build_contexts_exclude_local_environment_files() -> None:
    for relative_path in (
        ".dockerignore",
        "backend/.dockerignore",
        "frontend/.dockerignore",
    ):
        dockerignore = read_project_file(relative_path)

        assert ".env*" in dockerignore


def test_readme_marks_hosted_blueprint_as_review_only() -> None:
    readme = read_project_file("README.md")
    normalized_readme = " ".join(readme.split())

    assert "## Hosted production package" in readme
    assert "does not provision" in normalized_readme
    assert "`/live`" in readme
    assert "does not run Alembic" in normalized_readme
    assert "pooled Neon connection" in normalized_readme
    assert "direct Neon connection" in normalized_readme
