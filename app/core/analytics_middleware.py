"""Per-request analytics middleware.

Fires one PostHog event per API request. The distinct id is the authenticated
user id when a valid access token is present, otherwise the client IP, so events
tie back to users where possible and to a stable anonymous id otherwise.

Health checks and CORS preflight (OPTIONS) requests are skipped to keep the
event stream meaningful. When PostHog is not configured ``capture_event`` is a
no-op, so this middleware adds only a cheap header parse per request.
"""

import time

import jwt
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.analytics import capture_event
from app.core.limiter import client_ip
from app.core.security import decode_access_token

_SKIP_PATHS = {"/health", "/api/v1/health"}


def _distinct_id(request: Request) -> str:
    """User id from a valid Bearer token, else the client IP."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token:
        try:
            return str(decode_access_token(token))
        except jwt.InvalidTokenError:
            pass
    return client_ip(request)


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
