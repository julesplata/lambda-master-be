"""Sentry error tracking for the API and the purge job.

``init_error_tracking`` does nothing unless SENTRY_DSN is set, so local dev and
tests send nothing. With it set, Sentry receives the API's unhandled exceptions
and 5xx responses, and the purge job's cron check-ins.

Sentry's defaults would send this app's secrets and visitors' text, so five
things are changed. Each leak below was reproduced with sentry-sdk 2.74 and
events kept in memory:

- Request headers are dropped except User-Agent. The SDK's own filter only knows
  generic names (Authorization, Cookie, X-Forwarded-For, X-Real-IP, X-Api-Key),
  while every request Cloudflare forwards carries X-Origin-Auth (ORIGIN_SECRET)
  and CF-Connecting-IP (the visitor's raw IP), and admin calls carry X-Admin-Key.
  X-Railway-Request-Id is kept as the ``railway_request_id`` tag: it is the id
  Railway's HTTP logs record, so an error leads straight to its log line.
- No local variables. When a database connection fails, frames inside
  SQLAlchemy and asyncpg hold the connection parameters, password included, and
  by default Sentry sends every frame's variables.
- No request bodies: feedback and report text is typed by visitors. For the
  same reason the database engine hides bound parameters (db/session.py),
  which SQLAlchemy otherwise writes into every database error message.
- Constraint violations: SQLAlchemy's asyncpg adapter error keeps Postgres's
  DETAIL in ``.detail``, and Sentry sends that as the error's value instead of
  ``str(error)``, which looks clean. For a CHECK or NOT NULL violation the
  DETAIL is the whole failing row ("Failing row contains (...)"), visitor text
  included, so the value is replaced; the errors around it in the chain still
  name the constraint. On SQLAlchemy 2.0 the DETAIL also reached the top-level
  message, hence the 2.1 floor in requirements.txt.
- No tracing. Transactions skip ``before_send``, so they would carry the headers.
"""

from typing import Any

import sentry_sdk

from app.core.config import settings

_KEPT_HEADERS = frozenset({"user-agent"})
_REQUEST_ID_HEADER = "x-railway-request-id"
_DRIVER_ERROR_MODULE = "sqlalchemy.dialects.postgresql.asyncpg"
_DRIVER_DETAIL_REMOVED = "[detail removed: it can quote the failing row]"


def init_error_tracking() -> None:
    """Start the Sentry client when SENTRY_DSN is set. Call it before the app is built."""
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.env,
        release=settings.railway_git_commit_sha or None,
        include_local_variables=False,
        max_request_body_size="never",
        before_send=scrub_event,
    )


def scrub_event(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    """Keep only User-Agent of the request headers, tag the Railway request id,
    and replace the driver error's detail (see the module docstring)."""
    request = event.get("request")
    if request and request.get("headers"):
        headers = {name.lower(): value for name, value in request["headers"].items()}
        request_id = headers.get(_REQUEST_ID_HEADER)
        if request_id:
            event.setdefault("tags", {})["railway_request_id"] = request_id
        request["headers"] = {
            name: value for name, value in headers.items() if name in _KEPT_HEADERS
        }
    for exception in (event.get("exception") or {}).get("values") or []:
        if exception.get("module") == _DRIVER_ERROR_MODULE:
            exception["value"] = _DRIVER_DETAIL_REMOVED
    return event
