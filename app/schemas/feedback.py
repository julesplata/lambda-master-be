import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

FeedbackCategory = Literal["bug", "idea", "praise", "other"]
FeedbackStatus = Literal["open", "reviewed"]
# The results-screen survey's answer (C5). Must match frontend Survey.tsx.
PreparingFor = Literal["interview", "current_job", "course", "curious"]


class FeedbackCreate(BaseModel):
    category: FeedbackCategory
    message: str = Field(min_length=1, max_length=2000)
    rating: int | None = Field(default=None, ge=1, le=5)
    # Sent to PostHog as a person property, not stored on the feedback row.
    preparing_for: PreparingFor | None = None


class FeedbackStatusUpdate(BaseModel):
    status: FeedbackStatus


class FeedbackPublic(BaseModel):
    id: uuid.UUID
    category: FeedbackCategory
    message: str
    rating: int | None
    status: FeedbackStatus
    created_at: datetime

    model_config = {"from_attributes": True}
