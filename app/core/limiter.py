from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.config import settings


def client_ip(request: Request) -> str:
    """Resolve the real client IP for rate limiting.

    Behind a proxy/load balancer (Railway, nginx, Cloudflare) the TCP peer is
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
