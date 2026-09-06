"""Compose the API and built React application on one HTTP origin."""

from pathlib import Path

from fastapi import FastAPI

from app.main import app as api_app


def create_hosted_app(
    frontend_directory: Path,
    *,
    api_application: FastAPI = api_app,
) -> FastAPI:
    """Return the Render entrypoint with API routes under ``/api``."""
    hosted_app = FastAPI(
        title="Ludex",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @hosted_app.get("/live")
    def live_check() -> dict[str, str]:
        """Probe only the combined HTTP process, never PostgreSQL."""
        return {"status": "live"}

    hosted_app.mount("/api", api_application)
    hosted_app.frontend(
        "/",
        directory=frontend_directory,
        fallback="index.html",
        check_dir=True,
    )
    return hosted_app
