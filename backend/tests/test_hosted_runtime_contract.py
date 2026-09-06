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


def service_named(blueprint: dict[str, Any], name: str) -> dict[str, Any]:
    services = blueprint.get("services")

    assert isinstance(services, list)
    return next(service for service in services if service["name"] == name)


def environment_by_key(service: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["key"]: entry for entry in service["envVars"]}


def test_render_blueprint_builds_the_vite_static_site() -> None:
    frontend = service_named(load_blueprint(), "ludex")

    assert frontend["type"] == "web"
    assert frontend["runtime"] == "static"
    assert frontend["rootDir"] == "frontend"
    assert frontend["buildCommand"] == "npm ci && npm run build"
    assert frontend["staticPublishPath"] == "./dist"
    assert frontend["autoDeployTrigger"] == "off"
    assert environment_by_key(frontend) == {
        "VITE_API_BASE_URL": {
            "key": "VITE_API_BASE_URL",
            "value": "/api",
        }
    }


def test_render_static_site_proxies_api_before_spa_fallback() -> None:
    frontend = service_named(load_blueprint(), "ludex")

    assert frontend["routes"] == [
        {
            "type": "rewrite",
            "source": "/api/*",
            "destination": "https://ludex-api.onrender.com/*",
        },
        {
            "type": "rewrite",
            "source": "/*",
            "destination": "/index.html",
        },
    ]


def test_render_blueprint_uses_paid_oregon_backend_and_shallow_probe() -> None:
    backend = service_named(load_blueprint(), "ludex-api")

    assert backend["type"] == "web"
    assert backend["runtime"] == "docker"
    assert backend["rootDir"] == "backend"
    assert backend["dockerfilePath"] == "./Dockerfile"
    assert backend["dockerCommand"] == "./render-start.sh"
    assert backend["plan"] == "0.5c-512mb"
    assert backend["region"] == "oregon"
    assert backend["numInstances"] == 1
    assert backend["healthCheckPath"] == "/live"
    assert backend["autoDeployTrigger"] == "off"


def test_render_blueprint_separates_public_values_and_runtime_secrets() -> None:
    backend = service_named(load_blueprint(), "ludex-api")
    environment = environment_by_key(backend)

    assert environment["FRONTEND_ORIGIN"] == {
        "key": "FRONTEND_ORIGIN",
        "value": "https://ludex.onrender.com",
    }
    assert environment["ACCESS_SESSION_COOKIE_SECURE"] == {
        "key": "ACCESS_SESSION_COOKIE_SECURE",
        "value": "true",
    }
    for key in (
        "DATABASE_URL",
        "STEAM_API_KEY",
        "IGDB_CLIENT_ID",
        "IGDB_CLIENT_SECRET",
    ):
        assert environment[key] == {"key": key, "sync": False}

    assert "GEMINI_API_KEY" not in environment


def test_render_start_does_not_run_migrations_in_web_worker() -> None:
    startup = read_project_file("backend/render-start.sh")

    assert "set -eu" in startup
    assert 'port="${PORT:-8000}"' in startup
    assert '--port "$port"' in startup
    assert "alembic" not in startup


def test_docker_build_contexts_exclude_local_environment_files() -> None:
    for relative_path in (
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
