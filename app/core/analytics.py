"""PostHog product analytics.

A single module-level client, created only when ``posthog_api_key`` is set. When
the key is empty every helper here is a no-op so local dev and tests emit no
events and make no network calls.

The PostHog SDK batches events and flushes them on its own background thread, so
``capture`` only enqueues — it never blocks the request handler on a network
round-trip.
"""

from posthog import Posthog

from app.core.config import settings

_client: Posthog | None = None


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


def capture_event(
    distinct_id: str,
    event: str,
    properties: dict[str, object] | None = None,
) -> None:
    """Enqueue an event. No-op when analytics is not configured."""
    if _client is None:
        return
    _client.capture(
        distinct_id=distinct_id,
        event=event,
        properties=properties or {},
    )
