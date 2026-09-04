"""Smoke tests: the app imports, wires every router, and answers /health.

These deliberately touch no database. Standing a Postgres service up in CI is a
separate piece of work from having a check that runs on every PR, and most of
what breaks in this codebase (a bad response_model, a duplicated route path, an
import cycle) breaks at import time, before any query is issued.
"""

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

    assert f"{settings.api_v1_prefix}/questions" in schema["paths"]
    assert f"{settings.api_v1_prefix}/quiz-attempts" in schema["paths"]


def test_unknown_route_is_not_found():
    with TestClient(app) as client:
        response = client.get(f"{settings.api_v1_prefix}/no-such-endpoint")

    assert response.status_code == 404
