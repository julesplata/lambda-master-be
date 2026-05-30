import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.question import Difficulty, QuestionDetail

# "random" samples fresh questions (default); "review" pulls the user's questions
# that are due for spaced-repetition revision (see user_question_stats).
AttemptMode = Literal["random", "review"]


class AttemptCreate(BaseModel):
    question_count: int = Field(gt=0, le=100)
    difficulty: Difficulty | None = None
    mode: AttemptMode = "random"


class AttemptCreateResponse(BaseModel):
    attempt_id: uuid.UUID
    started_at: datetime


class AnswerSubmit(BaseModel):
    question_id: uuid.UUID
    selected_option_id: uuid.UUID


class AnswerResult(BaseModel):
    correct: bool
    explanation: str | None = None


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
    xp_earned: int
    total_xp: int
    level: int
    current_streak: int
