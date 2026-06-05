import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

ReportReason = Literal["incorrect_answer", "typo", "unclear", "outdated", "other"]
ReportStatus = Literal["open", "resolved", "dismissed"]


class ReportCreate(BaseModel):
    reason: ReportReason
    comment: str | None = Field(default=None, max_length=2000)
    attempt_id: uuid.UUID | None = None


class ReportStatusUpdate(BaseModel):
    status: ReportStatus


class ReportPublic(BaseModel):
    id: uuid.UUID
    question_id: uuid.UUID
    # Human-readable identifiers for the admin view, joined from the question.
    question_title: str
    category: str | None
    attempt_id: uuid.UUID | None
    reason: ReportReason
    comment: str | None
    status: ReportStatus
    created_at: datetime
