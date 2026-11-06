"""GET /ready answers 200 only while the database answers.

CI has no Postgres, so the session is swapped for a stub that answers, fails or
hangs the way a real database can.
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

from app.api.v1 import routes
from app.core.config import settings
from app.db.session import get_session
from app.main import app

READY_URL = f"{settings.api_v1_prefix}/ready"


class StubSession:
    def __init__(self, error: Exception | None = None, delay_seconds: float = 0):
        self.error = error
        self.delay_seconds = delay_seconds

    async def execute(self, statement):
        await asyncio.sleep(self.delay_seconds)
        if self.error:
            raise self.error


@pytest.fixture
def client_with_session():
    def build(session: StubSession) -> TestClient:
        async def override():
            yield session

        app.dependency_overrides[get_session] = override
        return TestClient(app)

    yield build
    app.dependency_overrides.pop(get_session, None)


def test_ready_while_the_database_answers(client_with_session):
    response = client_with_session(StubSession()).get(READY_URL)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_not_ready_when_the_database_refuses(client_with_session):
    session = StubSession(error=ConnectionRefusedError("connection refused"))

    assert client_with_session(session).get(READY_URL).status_code == 503


def test_not_ready_when_the_database_hangs(client_with_session, monkeypatch):
    monkeypatch.setattr(routes, "READY_TIMEOUT_SECONDS", 0.05)
    session = StubSession(delay_seconds=5)

    assert client_with_session(session).get(READY_URL).status_code == 503


def test_ready_needs_no_origin_secret(client_with_session, monkeypatch):
    # Railway's deploy healthcheck calls the service directly, not via Cloudflare.
    monkeypatch.setattr(settings, "origin_secret", "o" * 32)

    assert client_with_session(StubSession()).get(READY_URL).status_code == 200
