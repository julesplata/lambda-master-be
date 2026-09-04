"""Per-request analytics middleware.

Fires one PostHog event per API request. The distinct id is the authenticated
user id when a valid access token is present, otherwise a salted hash of the
client IP, so events tie back to users where possible and to a stable
pseudonymous id otherwise. The raw IP never leaves the process: it is PII, and
in guest-only mode every single request would carry one.

Health checks and CORS preflight (OPTIONS) requests are skipped to keep the
event stream meaningful. When PostHog is not configured ``capture_event`` is a
no-op, so this middleware adds only a cheap header parse per request.
"""

import hashlib
import hmac
import secrets
import time

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.analytics import capture_event
from app.core.config import settings
from app.core.limiter import client_ip
from app.core.security import decode_access_token

_SKIP_PATHS = {"/health", "/api/v1/health"}

# Fallback key used when ANALYTICS_IP_SALT is unset. An *unsalted* IP hash is not
# anonymisation — the whole IPv4 space is ~4 billion candidates, so a digest can
# be brute-forced back to an address in seconds — hence a random key rather than
# a constant or an empty one. The cost of the fallback is that ids stop being
# comparable across restarts and across instances, so set ANALYTICS_IP_SALT in
# production to keep a guest's requests stitched together.
_FALLBACK_IP_SALT = secrets.token_urlsafe(32)


def _anonymous_id(request: Request) -> str:
    """A stable, non-reversible id derived from the client IP.

    Keyed HMAC-SHA256, truncated: with the salt held server-side the digest is
    not reversible by whoever holds the analytics data, while the same IP still
    maps to the same id, so per-visitor funnels keep working. The ``anon-``
    prefix keeps these ids from ever being mistaken for the user UUIDs that
    authenticated requests report.
    """
    salt = settings.analytics_ip_salt or _FALLBACK_IP_SALT
    digest = hmac.new(
        salt.encode(), client_ip(request).encode(), hashlib.sha256
    ).hexdigest()
    return f"anon-{digest[:32]}"


def _distinct_id(request: Request) -> str:
    """User id from a valid Bearer token, else a salted hash of the client IP."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token:
        try:
            return str(decode_access_token(token))
        except jwt.InvalidTokenError:
            pass
    return _anonymous_id(request)


class AnalyticsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if request.method == "OPTIONS" or request.url.path in _SKIP_PATHS:
            return await call_next(request)

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000

        capture_event(
            distinct_id=_distinct_id(request),
            event="api_request",
            properties={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
            },
        )
        return response
