"""A visitor who refuses analytics must not show up in the server-side event stream.

The privacy policy promises that declining the consent banner, or browsing with
Global Privacy Control on, also stops the per-request metrics.
"""

import pytest
from fastapi.testclient import TestClient

import app.core.analytics_middleware as middleware
from app.main import app

client = TestClient(app)


@pytest.fixture
def captured(monkeypatch):
    events: list[dict] = []
    monkeypatch.setattr(middleware, "analytics_enabled", lambda: True)
    monkeypatch.setattr(middleware, "capture_event", lambda **event: events.append(event))
    return events


def test_request_is_captured_by_default(captured):
    client.get("/api/v1/does-not-exist")

    assert len(captured) == 1


@pytest.mark.parametrize(
    "headers",
    [{"X-Analytics-Opt-Out": "1"}, {"Sec-GPC": "1"}],
    ids=["banner-decline", "global-privacy-control"],
)
def test_refusal_skips_capture(captured, headers):
    client.get("/api/v1/does-not-exist", headers=headers)

    assert captured == []


def test_other_header_values_do_not_opt_out(captured):
    client.get("/api/v1/does-not-exist", headers={"X-Analytics-Opt-Out": "0", "Sec-GPC": "0"})

    assert len(captured) == 1
