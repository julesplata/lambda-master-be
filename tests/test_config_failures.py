"""Missing or dev-only configuration must fail at startup, never per request.

An empty JWT_SECRET makes PyJWT raise InvalidKeyError, which is not an
InvalidTokenError; left uncaught, every request carrying a stale Bearer token
became a 500. These tests touch no database.
"""

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api import deps
from app.core import analytics
from app.core.config import Settings, settings
from app.main import app

STRONG = "s" * 32
PRODUCTION_OK = {
    "env": "production",
    "debug": False,
    "auth_bypass_user_id": "",
    "jwt_secret": STRONG,
    "admin_api_key": STRONG,
    "cors_origins": ["https://app.example.com"],
}


def bearer(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.fixture
def stale_token():
    # Signed under some other secret, like a token left over in localStorage.
    return jwt.encode({"sub": "x", "type": "access"}, "old-" + STRONG, "HS256")


@pytest.fixture
def no_jwt_secret(monkeypatch):
    monkeypatch.setattr(settings, "jwt_secret", "")


class RecordingClient:
    def __init__(self):
        self.events = []

    def capture(self, **event):
        self.events.append(event)

    def shutdown(self):
        pass


def test_analytics_treats_unverifiable_token_as_anonymous(
    monkeypatch, no_jwt_secret, stale_token
):
    recorder = RecordingClient()
    monkeypatch.setattr(analytics, "_client", recorder)

    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(
            f"{settings.api_v1_prefix}/no-such-endpoint",
            headers={"Authorization": f"Bearer {stale_token}"},
        )

    assert response.status_code == 404
    assert [e["distinct_id"][:5] for e in recorder.events] == ["anon-"]


def test_user_auth_without_jwt_secret_is_401(
    monkeypatch, no_jwt_secret, stale_token
):
    monkeypatch.setattr(settings, "auth_bypass_user_id", "")

    with pytest.raises(HTTPException) as exc_info:
        deps.get_current_user_id(bearer(stale_token))

    assert exc_info.value.status_code == 401


def test_admin_bearer_without_jwt_secret_falls_back_to_key(
    monkeypatch, no_jwt_secret, stale_token
):
    monkeypatch.setattr(settings, "admin_api_key", STRONG)

    with pytest.raises(HTTPException) as exc_info:
        deps.require_admin(x_admin_key=None, credentials=bearer(stale_token))
    assert exc_info.value.status_code == 401

    deps.require_admin(x_admin_key=STRONG, credentials=bearer(stale_token))


def test_production_settings_accept_a_safe_config():
    Settings(_env_file=None, **PRODUCTION_OK)


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"jwt_secret": ""}, "JWT_SECRET"),
        ({"admin_api_key": "short"}, "ADMIN_API_KEY"),
        ({"debug": True}, "DEBUG"),
        ({"auth_bypass_user_id": "00000000-0000-0000-0000-000000000000"}, "AUTH_BYPASS"),
        ({"cors_origins": ["http://localhost:5173"]}, "CORS_ORIGINS"),
        ({"env": "staging", "jwt_secret": ""}, "JWT_SECRET"),
    ],
)
def test_deployed_settings_refuse_unsafe_config(override, message):
    with pytest.raises(ValidationError, match=message):
        Settings(_env_file=None, **{**PRODUCTION_OK, **override})


def test_development_settings_allow_missing_secrets():
    Settings(_env_file=None, env="development", jwt_secret="", admin_api_key="")
