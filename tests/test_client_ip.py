"""client_ip must not let a client choose its own rate-limit bucket.

Through Cloudflare, CF-Connecting-IP is the client, but only on requests that
carry the origin secret Cloudflare adds: anyone can reach Railway's edge
directly and send that header themselves. Without the secret, a proxy appends
the address it saw to X-Forwarded-For, after anything the client sent, so only
the rightmost trusted_proxy_hops entries can be believed.
"""

import pytest
from starlette.requests import Request

from app.core.config import settings
from app.core.limiter import client_ip

PEER = "10.0.0.2"  # the TCP peer, i.e. the edge proxy's own address
SECRET = "o" * 32
CLOUDFLARE_EGRESS = "172.68.0.1"  # what Railway's edge appends behind Cloudflare


def make_request(*forwarded_for: str, extra: dict[str, str] | None = None) -> Request:
    headers = [(b"x-forwarded-for", value.encode()) for value in forwarded_for]
    headers += [(name.encode(), value.encode()) for name, value in (extra or {}).items()]
    return Request({"type": "http", "headers": headers, "client": (PEER, 443)})


def via_cloudflare(client: str, origin_auth: str = SECRET) -> Request:
    return make_request(
        f"{client}, {CLOUDFLARE_EGRESS}",
        extra={"cf-connecting-ip": client, "x-origin-auth": origin_auth},
    )


@pytest.fixture
def origin_secret(monkeypatch):
    monkeypatch.setattr(settings, "origin_secret", SECRET)
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)


@pytest.fixture
def hops(monkeypatch):
    def set_hops(value: int) -> None:
        monkeypatch.setattr(settings, "trusted_proxy_hops", value)

    return set_hops


def test_uses_the_entry_the_edge_appended(hops):
    hops(1)

    assert client_ip(make_request("203.0.113.9")) == "203.0.113.9"


def test_spoofed_leading_entries_are_ignored(hops):
    hops(1)

    # Each request fakes a different address; the edge still appends the real one.
    ips = {client_ip(make_request(f"{n}.1.1.1, 203.0.113.9")) for n in range(7)}

    assert ips == {"203.0.113.9"}


def test_a_separate_client_sent_header_line_is_not_preferred(hops):
    hops(1)

    assert client_ip(make_request("6.6.6.6", "203.0.113.9")) == "203.0.113.9"


def test_counts_multiple_hops_from_the_right(hops):
    hops(2)

    request = make_request("6.6.6.6, 203.0.113.9, 172.16.0.5")

    assert client_ip(request) == "203.0.113.9"


def test_chain_shorter_than_hops_falls_back_to_the_peer(hops):
    hops(2)

    assert client_ip(make_request("6.6.6.6")) == PEER


def test_zero_hops_ignores_the_header(hops):
    hops(0)

    assert client_ip(make_request("6.6.6.6, 203.0.113.9")) == PEER


def test_no_header_uses_the_peer(hops):
    hops(1)

    assert client_ip(make_request()) == PEER


def test_through_cloudflare_the_client_is_cf_connecting_ip(origin_secret):
    assert client_ip(via_cloudflare("203.0.113.9")) == "203.0.113.9"


def test_without_the_secret_cf_connecting_ip_is_not_believed(origin_secret):
    # A request sent straight to Railway's edge, with a wrong or missing secret.
    forged = make_request(
        "6.6.6.6, 198.51.100.4", extra={"cf-connecting-ip": "6.6.6.6"}
    )

    assert client_ip(forged) == "198.51.100.4"
    assert client_ip(via_cloudflare("6.6.6.6", origin_auth="guess")) == CLOUDFLARE_EGRESS


def test_unset_secret_never_matches_a_missing_header(monkeypatch):
    monkeypatch.setattr(settings, "origin_secret", "")
    monkeypatch.setattr(settings, "trusted_proxy_hops", 1)

    request = make_request(
        "198.51.100.4", extra={"cf-connecting-ip": "6.6.6.6", "x-origin-auth": ""}
    )

    assert client_ip(request) == "198.51.100.4"
