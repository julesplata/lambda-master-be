import re
import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.question import Difficulty, QuestionDetail

# Where a quiz was started (C3). Must match QuizSource in frontend/src/types.ts.
QuizSource = Literal[
    "home_hero",
    "home_cta",
    "home_sample",
    "header",
    "topics_list",
    "topic_guide",
    "quiz_landing",
    "topic_picker",
    "topic_grid",
    "dashboard",
    "retry_start",
    "results_retry",
    "results_level_up",
    "results_suggestion",
    "link",
    "other",
]
_QUIZ_SOURCES = frozenset(QuizSource.__args__)
# A DNS host name: letters, digits, dots and hyphens, at most 253 characters.
_HOST_NAME = re.compile(r"[a-z0-9.-]{1,253}")


class AttemptCreate(BaseModel):
    # The frontend always asks for 10. This is an open endpoint, so the ceiling
    # stays close to what a real quiz needs rather than what the bank could serve.
    question_count: int = Field(gt=0, le=20)
    difficulty: Difficulty | None = None
    category: str | None = None
    # Questions this browser has answered, oldest first (B2). Used once to put
    # unseen questions first and the longest-ago answered next. The list itself
    # is never stored or logged: only which of this quiz's questions were in it
    # (quiz_attempts.repeated_question_ids, C2). The cap keeps the request
    # small; ids that fall off the front are the oldest, so treating them as
    # unseen is the right order.
    seen_question_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    # Where the quiz was started (C3). A value outside QuizSource is stored as
    # "other" rather than refused, so a stale or odd link still starts a quiz.
    source: QuizSource | None = None
    # The other site the visitor arrived from, host name only, for the
    # quiz_started event. Not stored. Anything that is not a host name is
    # dropped rather than refused.
    referrer_host: str | None = None

    @field_validator("source", mode="before")
    @classmethod
    def unknown_source_is_other(cls, value: object) -> object:
        if value is None or value in _QUIZ_SOURCES:
            return value
        return "other"

    @field_validator("referrer_host", mode="before")
    @classmethod
    def host_name_or_nothing(cls, value: object) -> str | None:
        if not isinstance(value, str):
            return None
        host = value.lower()
        return host if _HOST_NAME.fullmatch(host) else None


class AttemptCreateResponse(BaseModel):
    attempt_id: uuid.UUID
    started_at: datetime


class AnswerSubmit(BaseModel):
    question_id: uuid.UUID
    selected_option_id: uuid.UUID
    # Time on the question, stored on the answer (C2) and sent to PostHog with
    # question_answered. Capped at an hour so one request cannot report nonsense.
    time_spent_ms: int | None = Field(default=None, ge=0, le=3_600_000)


class AnswerResult(BaseModel):
    correct: bool
    explanation: str | None = None
    correct_option_id: uuid.UUID | None = None


class AttemptQuestion(QuestionDetail):
    """A question as it appears inside an attempt, with this attempt's answer.

    The answer fields let a client that lost its in-memory state (a page
    refresh) rebuild it from the server. They are all null until the question
    is answered, and `correct_option_id` / `explanation` stay null until then
    on purpose: an attempt is readable by anyone holding its id, so filling
    them in early would hand out the answer key to the rest of the quiz.
    """

    selected_option_id: uuid.UUID | None = None
    is_correct: bool | None = None
    correct_option_id: uuid.UUID | None = None
    explanation: str | None = None


class AttemptDetail(BaseModel):
    attempt_id: uuid.UUID
    started_at: datetime
    completed_at: datetime | None
    total_questions: int
    answered_count: int
    score: int | None
    questions: list[AttemptQuestion]


class AttemptComplete(BaseModel):
    score: int
    total_questions: int
    percentage: float
