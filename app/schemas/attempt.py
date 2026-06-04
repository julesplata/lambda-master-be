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


class AttemptDetail(BaseModel):
    attempt_id: uuid.UUID
    started_at: datetime
    completed_at: datetime | None
    total_questions: int
    answered_count: int
    score: int | None
    questions: list[QuestionDetail]


class AttemptComplete(BaseModel):
    score: int
    total_questions: int
    percentage: float
