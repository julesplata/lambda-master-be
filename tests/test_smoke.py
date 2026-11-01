"""Smoke tests: the app imports, wires every router, and answers /health.

These deliberately touch no database. Standing a Postgres service up in CI is a
separate piece of work from having a check that runs on every PR, and most of
what breaks in this codebase (a bad response_model, a duplicated route path, an
import cycle) breaks at import time, before any query is issued.
"""

import os
import subprocess
import sys
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def test_health_check_returns_ok():
    with TestClient(app) as client:
        response = client.get(f"{settings.api_v1_prefix}/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_schema_builds():
    schema = app.openapi()

    assert f"{settings.api_v1_prefix}/questions/bulk" in schema["paths"]
    assert f"{settings.api_v1_prefix}/quiz-attempts" in schema["paths"]


def test_public_question_reads_are_not_mounted():
    # GET /questions/{id} returned options in stored order, which leaked the
    # answer key. Questions are served only through attempts, which shuffle.
    paths = app.openapi()["paths"]

    assert "get" not in paths.get(f"{settings.api_v1_prefix}/questions", {})
    assert "get" not in paths.get(f"{settings.api_v1_prefix}/questions/{{question_id}}", {})


def test_unknown_route_is_not_found():
    with TestClient(app) as client:
        response = client.get(f"{settings.api_v1_prefix}/no-such-endpoint")

    assert response.status_code == 404


DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


def test_api_docs_are_served_in_development():
    with TestClient(app) as client:
        for path in DOCS_PATHS:
            assert client.get(path).status_code == 200, path


def test_api_docs_are_hidden_outside_development():
    # The app is built at import time, so check a fresh import under ENV=production.
    probe = (
        "from fastapi.testclient import TestClient\n"
        "from app.main import app\n"
        "client = TestClient(app)\n"
        f"print([client.get(p).status_code for p in {DOCS_PATHS!r}])\n"
    )
    env = {
        **os.environ,
        "ENV": "production",
        "DEBUG": "false",
        "AUTH_BYPASS_USER_ID": "",
        "JWT_SECRET": "j" * 32,
        "ADMIN_API_KEY": "k" * 32,
        "CORS_ORIGINS": "https://www.example.com",
    }
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        text=True,
        env=env,
        cwd=Path(__file__).resolve().parents[1],
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "[404, 404, 404]"
