import ipaddress

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.config import settings
from app.core.edge import came_through_cloudflare

# One IPv6 host normally controls a whole /64 (2**64 addresses), so keying on
# the full address would let it pick a fresh bucket for every request. Narrow
# to /56 if abuse turns up from residential ranges, which are often given one.
IPV6_PREFIX = 64


def bucket(ip: str) -> str:
    """Rate-limit key for an address: IPv4 as-is, IPv6 grouped by network.

    The address is also put in canonical form, since one IPv6 address has many
    spellings (2001:DB8::1, 2001:db8:0:0::1) and each would get its own bucket.
    IPv4-mapped addresses (::ffff:203.0.113.9) are IPv4 clients and keyed as
    such; grouping them by /64 would put every one of them in ::/64.
    Anything that doesn't parse (e.g. Starlette's "testclient") is returned
    unchanged.
    """
    try:
        addr = ipaddress.ip_address(ip.strip())
    except ValueError:
        return ip
    if addr.version == 6:
        if addr.ipv4_mapped:
            return str(addr.ipv4_mapped)
        return str(ipaddress.ip_network(f"{addr}/{IPV6_PREFIX}", strict=False))
    return str(addr)


def client_ip(request: Request) -> str:
    """The client's rate-limit bucket (and the input to the analytics id).

    The resolved address, grouped by bucket(), so no route can key on a raw
    IPv6 address. For analytics this means one id per IPv6 /64 rather than one
    per address, which also stops the id changing whenever the OS rotates its
    temporary (privacy) address.
    """
    return bucket(_resolve_client_ip(request))


def _resolve_client_ip(request: Request) -> str:
    """Resolve the real client IP.

    In production every request comes through Cloudflare, which writes the
    client's address to CF-Connecting-IP. That header is only believed when the
    request also carries the origin secret Cloudflare adds (see core/edge.py),
    because Railway's edge can be reached directly and a client going that way
    can send any CF-Connecting-IP it likes.

    Everything below handles requests without the secret: local dev, or a
    deploy without ORIGIN_SECRET. Behind a proxy/load balancer the TCP peer is
    the proxy, so the per-IP limit would be shared across all users. Each proxy
    appends the address it received the request from to X-Forwarded-For, but
    whatever the client sent comes first, so every entry left of the ones our
    own proxies wrote is attacker-controlled. We therefore count
    ``trusted_proxy_hops`` entries from the right and use that one.

    Getting the count wrong fails in one of two directions: too high and the
    client picks its own IP (the limit is bypassable); too low and we pick a
    proxy's IP (everyone shares one bucket). When the chain is shorter than
    the hop count the request did not come through our proxies, so we fall back
    to the TCP peer rather than trust any of it.
    """
    if came_through_cloudflare(request.headers):
        cloudflare_ip = request.headers.get("cf-connecting-ip", "").strip()
        if cloudflare_ip:
            return cloudflare_ip
    hops = settings.trusted_proxy_hops
    if hops:
        # getlist + join: a client can send its own separate X-Forwarded-For
        # line, and .get() would return that one instead of the proxy's.
        chain = [
            entry.strip()
            for header in request.headers.getlist("x-forwarded-for")
            for entry in header.split(",")
            if entry.strip()
        ]
        if len(chain) >= hops:
            return chain[-hops]
    return get_remote_address(request)


# Every limit is keyed per client IP. There are deliberately no app-wide
# buckets: a shared counter is a kill switch (anyone who can send N requests
# locks every user out) and a hard ceiling on real traffic. Sustained abuse is
# bounded by each route's per-IP hourly limit instead, and distributed abuse
# belongs at the edge (WAF / Turnstile), not in a counter real users share.
#
# moving-window, not the default fixed-window: a fixed window lets a client
# spend its whole budget at the end of one window and again at the start of the
# next, doubling the effective burst.
#
# When rate_limit_storage_uri is set (e.g. a Redis URL), counters are shared
# across instances; otherwise SlowAPI keeps per-process in-memory state. With
# shared storage, an outage falls back to in-memory counters instead of failing
# every request.
_limiter_kwargs = {}
if settings.rate_limit_storage_uri:
    _limiter_kwargs["storage_uri"] = settings.rate_limit_storage_uri
    _limiter_kwargs["in_memory_fallback_enabled"] = True

limiter = Limiter(
    key_func=client_ip,
    default_limits=[settings.rate_limit_default],
    strategy="moving-window",
    **_limiter_kwargs,
)
