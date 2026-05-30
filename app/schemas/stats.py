import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.question import Difficulty


class StatsOverview(BaseModel):
    """Top-line learning stats for the current user."""

    attempts_completed: int
    questions_answered: int
    questions_correct: int
    accuracy: float  # 0..1 over all answered questions; 0.0 when none answered
    questions_due: int  # cards due for spaced-repetition review right now
    xp: int
    level: int
    current_streak: int
    longest_streak: int


class TagAccuracy(BaseModel):
    tag: str
    answered: int
    correct: int
    accuracy: float


class DifficultyAccuracy(BaseModel):
    difficulty: Difficulty
    answered: int
    correct: int
    accuracy: float


class AttemptHistoryItem(BaseModel):
    attempt_id: uuid.UUID
    score: int
    total_questions: int
    percentage: float
    completed_at: datetime
