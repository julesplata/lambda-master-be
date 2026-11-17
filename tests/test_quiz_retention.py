"""Request limits and visitor ids for the quiz retention work (B2 to B4).

The question ordering and the question_answered event need Postgres, which CI
does not have, so they were checked against a local scratch database. These
cover what can be checked without one.
"""

import uuid

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from app.core import analytics
from app.schemas.attempt import AnswerSubmit, AttemptCreate


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


def test_seen_list_defaults_to_empty():
    assert AttemptCreate(question_count=10).seen_question_ids == []


def test_seen_list_accepts_500_ids():
    ids = [uuid.uuid4() for _ in range(500)]

    assert (
        len(AttemptCreate(question_count=10, seen_question_ids=ids).seen_question_ids)
        == 500
    )


def test_seen_list_over_500_is_rejected():
    ids = [uuid.uuid4() for _ in range(501)]

    with pytest.raises(ValidationError):
        AttemptCreate(question_count=10, seen_question_ids=ids)


@pytest.mark.parametrize("value", [-1, 3_600_001])
def test_time_spent_out_of_range_is_rejected(value):
    with pytest.raises(ValidationError):
        AnswerSubmit(
            question_id=uuid.uuid4(),
            selected_option_id=uuid.uuid4(),
            time_spent_ms=value,
        )


def test_time_spent_is_optional():
    body = AnswerSubmit(question_id=uuid.uuid4(), selected_option_id=uuid.uuid4())

    assert body.time_spent_ms is None


def test_visitor_header_is_read():
    visitor = uuid.uuid4()

    assert analytics.visitor_id(make_request({"X-Visitor-Id": str(visitor)})) == visitor


@pytest.mark.parametrize("value", ["", "not-a-uuid", "1" * 400])
def test_malformed_visitor_header_is_ignored(value):
    assert analytics.visitor_id(make_request({"X-Visitor-Id": value})) is None


@pytest.mark.parametrize(
    "refusal",
    [{"X-Analytics-Opt-Out": "1"}, {"Sec-GPC": "1"}],
    ids=["banner-decline", "global-privacy-control"],
)
def test_visitor_header_is_ignored_after_refusal(refusal):
    headers = {"X-Visitor-Id": str(uuid.uuid4()), **refusal}

    assert analytics.visitor_id(make_request(headers)) is None


def test_events_use_the_visitor_id(recorder):
    visitor = uuid.uuid4()

    analytics.track(
        make_request({"X-Visitor-Id": str(visitor)}), "quiz_started", {"a": 1}
    )

    event = recorder.events[0]
    assert event["distinct_id"] == f"visitor-{visitor}"
    assert event["properties"] == {"a": 1, "id_source": "visitor"}


def test_events_fall_back_to_the_ip_hash(recorder):
    analytics.track(make_request({"X-Visitor-Id": "junk"}), "quiz_started")

    event = recorder.events[0]
    assert event["distinct_id"].startswith("anon-")
    assert event["properties"] == {"id_source": "ip"}
