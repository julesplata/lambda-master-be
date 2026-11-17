"""Request parsing and event properties for the data quality work (C1 to C5).

What the database stores, the analytics views and the stats endpoint need
Postgres, which CI does not have, so they were checked against a local scratch
database. These cover what can be checked without one.
"""

import uuid

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from app.api.v1.endpoints.attempts import _first_time
from app.core import analytics
from app.models import QuizAttempt
from app.schemas.attempt import AttemptCreate
from app.schemas.feedback import FeedbackCreate


class RecordingClient:
    def __init__(self):
        self.events = []

    def capture(self, **event):
        self.events.append(event)


@pytest.fixture
def recorder(monkeypatch):
    client = RecordingClient()
    monkeypatch.setattr(analytics, "_client", client)
    return client


def make_request(headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/quiz-attempts",
            "headers": [(k.lower().encode(), v.encode()) for k, v in headers.items()],
            "client": ("203.0.113.7", 1234),
        }
    )


def test_internal_header_marks_events(recorder):
    analytics.track(make_request({"X-Internal": "1"}), "quiz_started")

    assert recorder.events[0]["properties"]["internal"] is True


@pytest.mark.parametrize("value", ["0", "true", ""])
def test_other_internal_values_are_not_internal(value):
    assert analytics.is_internal(make_request({"X-Internal": value})) is False


def test_internal_is_independent_of_analytics_refusal():
    request = make_request({"X-Internal": "1", "X-Analytics-Opt-Out": "1"})

    assert analytics.is_internal(request) is True


def test_known_source_is_kept():
    assert AttemptCreate(question_count=10, source="topic_guide").source == "topic_guide"


@pytest.mark.parametrize("value", ["somewhere_new", "x" * 400, 42])
def test_unknown_source_is_stored_as_other(value):
    assert AttemptCreate(question_count=10, source=value).source == "other"


def test_source_is_optional():
    assert AttemptCreate(question_count=10).source is None


def test_referrer_host_is_lowercased():
    body = AttemptCreate(question_count=10, referrer_host="WWW.Google.com")

    assert body.referrer_host == "www.google.com"


@pytest.mark.parametrize(
    "value",
    ["https://www.google.com/search?q=x", "a" * 254, "host name", "", 7],
)
def test_anything_but_a_host_name_is_dropped(value):
    assert AttemptCreate(question_count=10, referrer_host=value).referrer_host is None


def test_first_time_reads_the_stored_repeats():
    repeat, fresh = uuid.uuid4(), uuid.uuid4()
    attempt = QuizAttempt(repeated_question_ids=[repeat])

    assert _first_time(attempt, repeat) is False
    assert _first_time(attempt, fresh) is True


def test_first_time_is_unknown_before_repeats_were_recorded():
    assert _first_time(QuizAttempt(repeated_question_ids=None), uuid.uuid4()) is None


def test_survey_answer_is_one_of_four():
    body = FeedbackCreate(category="other", message="m", preparing_for="interview")

    assert body.preparing_for == "interview"
    with pytest.raises(ValidationError):
        FeedbackCreate(category="other", message="m", preparing_for="fun")
