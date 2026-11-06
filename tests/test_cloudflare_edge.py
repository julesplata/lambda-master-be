"""Requests must come through Cloudflare, and are keyed on Cloudflare's client IP.

Railway's edge serves the API to anyone who connects to it directly. Once
ORIGIN_SECRET is set, only requests carrying the secret Cloudflare adds are
served; anything else is a request that went around Cloudflare. These tests
touch no database; the admin key exchange is used because it is rate limited
and needs none.
"""

import pytest
from fastapi.testclient import TestClient

from app.core.config import ADMIN_API_KEY_MIN_LENGTH, settings
from app.core.limiter import limiter
from app.main import app

SECRET = "o" * 32
SESSION_URL = f"{settings.api_v1_prefix}/admin/session"
HEALTH_URL = f"{settings.api_v1_prefix}/health"
CLOUDFLARE_EGRESS = "172.68.0.1"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(settings, "origin_secret", SECRET)
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)
    monkeypatch.setattr(settings, "admin_api_key", "k" * ADMIN_API_KEY_MIN_LENGTH)
    monkeypatch.setattr(settings, "jwt_secret", "test-secret-" + "x" * 32)
    limiter.reset()
    with TestClient(app) as test_client:
        yield test_client
    limiter.reset()


def cloudflare_headers(client_address: str, forged: str = "6.6.6.6") -> dict[str, str]:
    # What reaches the app via Cloudflare: the client's own X-Forwarded-For
    # entry, then the Cloudflare address Railway's edge appended.
    return {
        "X-Origin-Auth": SECRET,
        "CF-Connecting-IP": client_address,
        "X-Forwarded-For": f"{forged}, {client_address}, {CLOUDFLARE_EGRESS}",
    }


def test_request_without_the_secret_is_refused(client):
    direct = client.post(SESSION_URL, json={"key": "x"}, headers={"CF-Connecting-IP": "6.6.6.6"})
    wrong = client.post(SESSION_URL, json={"key": "x"}, headers={"X-Origin-Auth": "guess"})

    assert direct.status_code == 403
    assert wrong.status_code == 403


def test_request_through_cloudflare_is_served(client):
    response = client.post(SESSION_URL, json={"key": "x"}, headers=cloudflare_headers("203.0.113.1"))

    assert response.status_code == 401


def test_health_check_needs_no_secret(client):
    # Railway's deploy healthcheck calls the service directly.
    assert client.get(HEALTH_URL).status_code == 200


def test_no_secret_configured_means_no_enforcement(client, monkeypatch):
    monkeypatch.setattr(settings, "origin_secret", "")

    assert client.post(SESSION_URL, json={"key": "x"}).status_code == 401


def test_buckets_follow_cf_connecting_ip_not_the_cloudflare_address(client):
    # Every request below arrives from the same Cloudflare egress address, and
    # the first six forge a different X-Forwarded-For entry each time.
    statuses = [
        client.post(
            SESSION_URL, json={"key": "x"}, headers=cloudflare_headers("203.0.113.1", f"{n}.1.1.1")
        ).status_code
        for n in range(6)
    ]
    other_client = client.post(SESSION_URL, json={"key": "x"}, headers=cloudflare_headers("203.0.113.2"))

    assert statuses == [401] * 5 + [429]
    assert other_client.status_code == 401
