import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.question import Difficulty, QuestionDetail


class AttemptCreate(BaseModel):
    question_count: int = Field(gt=0, le=100)
    difficulty: Difficulty | None = None
    category: str | None = None


class AttemptCreateResponse(BaseModel):
    attempt_id: uuid.UUID
    started_at: datetime


class AnswerSubmit(BaseModel):
    question_id: uuid.UUID
    selected_option_id: uuid.UUID


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
