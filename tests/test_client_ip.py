"""client_ip must not let a client choose its own rate-limit bucket.

A proxy appends the address it saw to X-Forwarded-For, after anything the client
sent, so only the rightmost trusted_proxy_hops entries can be believed.
"""

import pytest
from starlette.requests import Request

from app.core.config import settings
from app.core.limiter import client_ip

PEER = "10.0.0.2"  # the TCP peer, i.e. the edge proxy's own address


def make_request(*forwarded_for: str) -> Request:
    headers = [(b"x-forwarded-for", value.encode()) for value in forwarded_for]
    return Request({"type": "http", "headers": headers, "client": (PEER, 443)})


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
