"""Rate limits must be per client, never one bucket every user shares.

A bucket keyed by a constant is a kill switch: whoever exhausts it locks every
real user out until the window resets. These tests touch no database; the admin
key exchange is used because it is rate limited and needs none.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import ADMIN_API_KEY_MIN_LENGTH, settings
from app.core.limiter import client_ip, limiter
from app.main import app

SESSION_URL = f"{settings.api_v1_prefix}/admin/session"
VALID_KEY = "k" * ADMIN_API_KEY_MIN_LENGTH


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)
    monkeypatch.setattr(settings, "admin_api_key", VALID_KEY)
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-" + "x" * 32)
    limiter.reset()
    with TestClient(app) as test_client:
        yield test_client
    limiter.reset()


def post_session(client: TestClient, ip: str, key: str = "wrong-key"):
    return client.post(
        SESSION_URL, json={"key": key}, headers={"X-Forwarded-For": ip}
    )


def test_every_route_limit_is_keyed_by_client_ip():
    limits = [limit for group in limiter._route_limits.values() for limit in group]

    assert limits, "expected decorated routes to register limits"
    assert all(limit.key_func is client_ip for limit in limits)


def test_exhausting_one_ip_does_not_block_another(client):
    statuses = [post_session(client, "203.0.113.1").status_code for _ in range(6)]

    assert statuses == [401] * 5 + [429]
    assert post_session(client, "203.0.113.2").status_code == 401
    assert post_session(client, "203.0.113.2", key=VALID_KEY).status_code == 200


def test_many_addresses_cannot_lock_everyone_out(client):
    # More calls than the old 50/hour app-wide admin bucket allowed.
    statuses = {post_session(client, f"198.51.100.{n}").status_code for n in range(60)}

    assert statuses == {401}
    assert post_session(client, "192.0.2.7", key=VALID_KEY).status_code == 200


def test_short_admin_key_disables_admin_routes(client, monkeypatch):
    short_key = "k" * (ADMIN_API_KEY_MIN_LENGTH - 1)
    monkeypatch.setattr(settings, "admin_api_key", short_key)

    session = post_session(client, "192.0.2.8", key=short_key)
    listing = client.get(
        f"{settings.api_v1_prefix}/admin/questions",
        headers={"X-Admin-Key": short_key},
    )

    assert session.status_code == 503
    assert listing.status_code == 503
