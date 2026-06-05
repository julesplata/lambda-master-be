from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.config import settings


def client_ip(request: Request) -> str:
    """Resolve the real client IP for rate limiting.

    Behind a proxy/load balancer (Railway, nginx, Cloudflare) the TCP peer is
    the proxy, so the per-IP limit would be shared across all users. When
    ``trust_forwarded_for`` is set we use the leftmost X-Forwarded-For entry,
    which the platform populates with the original client. This header is
    spoofable when the app is reachable directly, so the flag must be false in
    that case.
    """
    if settings.trust_forwarded_for:
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
    return get_remote_address(request)


def submit_global_key(request: Request) -> str:
    """Single shared bucket for a coarse, app-wide cap on open submissions."""
    return "submit-global"


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
