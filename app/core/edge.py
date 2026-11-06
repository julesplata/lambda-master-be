"""Telling requests that came through Cloudflare from ones that went around it.

Production is Cloudflare -> Railway's edge -> app. Railway's edge also serves our
domain to anyone who connects to it directly (``curl --resolve`` to a Railway
edge IP is enough; removing the *.up.railway.app domain does not change that),
so the network path proves nothing. Instead a Cloudflare Transform Rule sets
``X-Origin-Auth: <ORIGIN_SECRET>`` on every request it forwards, replacing any
value the client sent. A request with the right value came through Cloudflare,
which means its CF-Connecting-IP header was written by Cloudflare and is the
real client address.
"""

import secrets

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import settings

ORIGIN_AUTH_HEADER = "x-origin-auth"


def came_through_cloudflare(headers: Headers) -> bool:
    secret = settings.origin_secret
    # An unset secret must not match a missing header: "" == "".
    if not secret:
        return False
    return secrets.compare_digest(
        headers.get(ORIGIN_AUTH_HEADER, "").encode(), secret.encode()
    )


class RequireCloudflare:
    """Refuse (403) requests that skipped Cloudflare once ORIGIN_SECRET is set.

    Without this, a direct request still gets in. It cannot pick its own
    rate-limit bucket (client_ip ignores CF-Connecting-IP without the secret),
    but it skips Cloudflare's WAF and rate limiting rule entirely.

    ``exempt_paths`` is for the health check: Railway's deploy healthcheck calls
    the service directly, without the header, and a 403 there would stop every
    deploy from going live.
    """

    def __init__(self, app: ASGIApp, exempt_paths: frozenset[str]) -> None:
        self.app = app
        self.exempt_paths = exempt_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or not settings.origin_secret
            or scope["path"] in self.exempt_paths
            or came_through_cloudflare(Headers(scope=scope))
        ):
            await self.app(scope, receive, send)
            return
        response = JSONResponse({"detail": "Forbidden"}, status_code=403)
        await response(scope, receive, send)
