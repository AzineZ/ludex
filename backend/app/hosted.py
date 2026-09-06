"""Render entrypoint for the combined same-origin Ludex service."""

from pathlib import Path

from app.hosting import create_hosted_app


app = create_hosted_app(Path("/app/frontend-dist"))
