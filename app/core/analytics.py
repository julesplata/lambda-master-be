"""PostHog product analytics.

A single module-level client, created only when ``posthog_api_key`` is set. When
the key is empty every helper here is a no-op so local dev and tests emit no
events and make no network calls.

Endpoints report a handful of product events through ``track`` — a quiz started,
a quiz completed — and nothing else. There is deliberately no per-request event:
event volume would then scale with raw traffic, including 404s, 422s and 429s,
so one script looping a cheap GET could burn through the PostHog quota (the
free tier stops ingesting at 1M events a month, taking browser analytics down
with it). Tracking only successful product actions ties volume to real usage,
and the rate limits on those endpoints cap what one address can generate.

The distinct id is the authenticated user id when a valid access token is
present, otherwise a salted hash of the client IP, so events tie back to users
where possible and to a stable pseudonymous id otherwise. The raw IP never
leaves the process: it is PII, and in guest-only mode every event would carry
one.

A visitor who refused analytics is never tracked: the frontend sends
``X-Analytics-Opt-Out: 1`` once they decline the consent banner, and browsers
with Global Privacy Control on send ``Sec-GPC: 1``. These events run on
legitimate interest rather than consent (no cookie, no raw IP), and honouring
that refusal is what makes the objection in the privacy policy real.

Analytics must never fail a request: a token that cannot be verified for any
reason — including an empty or unusable JWT_SECRET — just makes the event
anonymous.

The PostHog SDK batches events and flushes them on its own background thread, so
``capture`` only enqueues — it never blocks the request handler on a network
round-trip.
"""

import hashlib
import hmac
import secrets

import jwt
from posthog import Posthog
from starlette.requests import Request

from app.core.config import settings
from app.core.limiter import client_ip
from app.core.security import decode_access_token

_client: Posthog | None = None

# Must match OPT_OUT_HEADER in frontend/lib/consent.ts.
_OPT_OUT_HEADER = "x-analytics-opt-out"

# Fallback key used when ANALYTICS_IP_SALT is unset. An *unsalted* IP hash is not
# anonymisation — the whole IPv4 space is ~4 billion candidates, so a digest can
# be brute-forced back to an address in seconds — hence a random key rather than
# a constant or an empty one. The cost of the fallback is that ids stop being
# comparable across restarts and across instances, so set ANALYTICS_IP_SALT in
# production to keep a guest's events stitched together.
_FALLBACK_IP_SALT = secrets.token_urlsafe(32)


def init_analytics() -> None:
    """Create the PostHog client if an API key is configured. Idempotent."""
    global _client
    if _client is not None or not settings.posthog_api_key:
        return
    _client = Posthog(
        project_api_key=settings.posthog_api_key,
        host=settings.posthog_host,
    )


def shutdown_analytics() -> None:
    """Flush queued events and release the client on app shutdown."""
    global _client
    if _client is not None:
        _client.shutdown()
        _client = None


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


def opted_out(request: Request) -> bool:
    """Whether the visitor refused analytics, explicitly or via Global Privacy Control."""
    headers = request.headers
    return headers.get(_OPT_OUT_HEADER) == "1" or headers.get("sec-gpc") == "1"


def _distinct_id(request: Request) -> str:
    """User id from a valid Bearer token, else a salted hash of the client IP."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() == "bearer" and token:
        try:
            return str(decode_access_token(token))
        except jwt.PyJWTError:
            # Not InvalidTokenError: a missing JWT_SECRET raises InvalidKeyError,
            # a sibling class.
            pass
    return _anonymous_id(request)


def track(
    request: Request,
    event: str,
    properties: dict[str, object] | None = None,
) -> None:
    """Enqueue a product event for the visitor behind ``request``.

    No-op when analytics is not configured or the visitor opted out. Call it
    only once the action has succeeded, so failed and rejected requests never
    cost an event.
    """
    if _client is None or opted_out(request):
        return
    _client.capture(
        distinct_id=_distinct_id(request),
        event=event,
        properties=properties or {},
    )
