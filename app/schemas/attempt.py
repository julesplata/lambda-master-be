import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.question import Difficulty, QuestionDetail


class AttemptCreate(BaseModel):
    # The frontend always asks for 10. This is an open endpoint, so the ceiling
    # stays close to what a real quiz needs rather than what the bank could serve.
    question_count: int = Field(gt=0, le=20)
    difficulty: Difficulty | None = None
    category: str | None = None
    # Questions this browser has answered, oldest first (B2). Used once to put
    # unseen questions first and the longest-ago answered next, then dropped:
    # never stored or logged. The cap keeps the request small; ids that fall off
    # the front are the oldest, so treating them as unseen is the right order.
    seen_question_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)


class AttemptCreateResponse(BaseModel):
    attempt_id: uuid.UUID
    started_at: datetime


class AnswerSubmit(BaseModel):
    question_id: uuid.UUID
    selected_option_id: uuid.UUID
    # Time on the question, sent to PostHog with question_answered and not
    # stored. Capped at an hour so one request cannot report nonsense.
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
