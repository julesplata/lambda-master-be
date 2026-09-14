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


def submit_global_key(request: Request) -> str:
    """Single shared bucket for a coarse, app-wide cap on open submissions."""
    return "submit-global"


def attempt_create_global_key(request: Request) -> str:
    """Single shared bucket capping app-wide anonymous attempt creation.

    Deliberately separate from submit_global_key: quiz starts are the app's
    primary user action and must not compete with reports and feedback for the
    same budget.
    """
    return "attempt-create-global"


def admin_session_global_key(request: Request) -> str:
    """Single shared bucket for the admin key exchange.

    The per-IP limit is bypassed by simply using more IPs, so this caps guessing
    across all of them. Note it is only as strong as the limiter's storage: with
    the in-memory default the cap is per-process and resets on redeploy, so a
    multi-instance deployment needs rate_limit_storage_uri pointed at Redis for
    this to mean anything.
    """
    return "admin-session-global"


# When rate_limit_storage_uri is set (e.g. a Redis URL), counters are shared
# across instances; otherwise SlowAPI falls back to per-process in-memory state.
_limiter_kwargs = {}
if settings.rate_limit_storage_uri:
    _limiter_kwargs["storage_uri"] = settings.rate_limit_storage_uri

limiter = Limiter(
    key_func=client_ip,
    default_limits=[settings.rate_limit_default],
    **_limiter_kwargs,
)
