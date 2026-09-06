from pathlib import Path

from fastapi import FastAPI, Response
from fastapi.testclient import TestClient

from app.hosting import create_hosted_app


def build_test_app(frontend_directory: Path) -> FastAPI:
    api_app = FastAPI()

    @api_app.post("/session")
    def create_session(response: Response) -> dict[str, str]:
        response.set_cookie(
            "ludex_access",
            "opaque-test-value",
            httponly=True,
            secure=True,
            samesite="lax",
            path="/",
        )
        return {"status": "created"}

    return create_hosted_app(
        frontend_directory,
        api_application=api_app,
    )


def test_combined_app_serves_frontend_and_forwards_api_mutations(
    tmp_path: Path,
) -> None:
    (tmp_path / "index.html").write_text(
        "<!doctype html><title>Ludex test frontend</title>",
        encoding="utf-8",
    )
    app = build_test_app(tmp_path)

    with TestClient(app, base_url="https://ludex.example") as client:
        frontend_response = client.get("/")
        session_response = client.post("/api/session")

    assert frontend_response.status_code == 200
    assert "Ludex test frontend" in frontend_response.text
    assert session_response.status_code == 200
    assert session_response.json() == {"status": "created"}
    assert session_response.headers["set-cookie"].startswith(
        "ludex_access=opaque-test-value; HttpOnly; Path=/; SameSite=lax; Secure"
    )


def test_combined_app_live_probe_is_shallow(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("Ludex", encoding="utf-8")
    app = build_test_app(tmp_path)

    with TestClient(app) as client:
        response = client.get("/live")

    assert response.status_code == 200
    assert response.json() == {"status": "live"}


def test_combined_app_does_not_turn_unknown_api_routes_into_spa_html(
    tmp_path: Path,
) -> None:
    (tmp_path / "index.html").write_text("Ludex", encoding="utf-8")
    app = build_test_app(tmp_path)

    with TestClient(app) as client:
        response = client.get(
            "/api/not-a-route",
            headers={"Accept": "text/html"},
        )

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
