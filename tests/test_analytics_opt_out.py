"""Server-side analytics: only product events, and never for a visitor who refused.

The privacy policy promises that declining the consent banner, or browsing with
Global Privacy Control on, also stops the server-side quiz events. Plain API
traffic must not produce events at all, so a script hammering an endpoint
cannot exhaust the PostHog quota.
"""

import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core import analytics
from app.core.config import settings
from app.main import app


class RecordingClient:
    def __init__(self):
        self.events = []

    def capture(self, **event):
        self.events.append(event)

    def shutdown(self):
        pass


@pytest.fixture
def recorder(monkeypatch):
    client = RecordingClient()
    monkeypatch.setattr(analytics, "_client", client)
    return client


def make_request(headers: dict[str, str] | None = None) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/quiz-attempts",
            "headers": [
                (k.lower().encode(), v.encode()) for k, v in (headers or {}).items()
            ],
            "client": ("203.0.113.7", 1234),
        }
    )


def test_event_is_tracked_by_default(recorder):
    analytics.track(make_request(), "quiz_started")

    assert [e["event"] for e in recorder.events] == ["quiz_started"]
    assert recorder.events[0]["distinct_id"].startswith("anon-")


@pytest.mark.parametrize(
    "headers",
    [{"X-Analytics-Opt-Out": "1"}, {"Sec-GPC": "1"}],
    ids=["banner-decline", "global-privacy-control"],
)
def test_refusal_skips_tracking(recorder, headers):
    analytics.track(make_request(headers), "quiz_started")

    assert recorder.events == []


def test_other_header_values_do_not_opt_out(recorder):
    analytics.track(
        make_request({"X-Analytics-Opt-Out": "0", "Sec-GPC": "0"}), "quiz_started"
    )

    assert len(recorder.events) == 1


@pytest.mark.parametrize("path", ["/no-such-endpoint", "/health"])
def test_plain_requests_send_no_events(recorder, path):
    with TestClient(app) as client:
        for _ in range(5):
            client.get(f"{settings.api_v1_prefix}{path}")

    assert recorder.events == []
