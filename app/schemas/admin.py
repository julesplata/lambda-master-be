"""Request/response schemas for the admin console.

These deliberately differ from the public question schemas in app/schemas/question.py:
the console needs the full record — is_correct on every option, the explanation,
timestamps — where the quiz surface must never see which option is correct.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.question import Difficulty


class AdminSessionCreate(BaseModel):
    key: str = Field(min_length=1)


class AdminSession(BaseModel):
    token: str
    expires_in_minutes: int


class AdminOption(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    text: str
    is_correct: bool


class AdminQuestion(BaseModel):
    """A question as the console sees it — full record, correct answer included."""

    id: uuid.UUID
    title: str
    description: str
    difficulty: Difficulty
    explanation: str | None
    category: str  # slug, matching what the write schemas accept
    options: list[AdminOption]
    updated_at: datetime
    archived_at: datetime | None


class AdminOptionWrite(BaseModel):
    text: str = Field(min_length=1)
    is_correct: bool = False


class AdminQuestionWrite(BaseModel):
    """Full replacement of a question and its option list.

    The console always sends the whole record (it edits a local draft and saves
    it as a unit), so create and update share one schema and updates replace the
    options wholesale rather than patching them individually.
    """

    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    difficulty: Difficulty
    explanation: str | None = None
    category: str = Field(min_length=1, max_length=50)
    options: list[AdminOptionWrite] = Field(min_length=2)

    @model_validator(mode="after")
    def at_least_one_correct(self) -> "AdminQuestionWrite":
        if not any(option.is_correct for option in self.options):
            raise ValueError("at least one option must be marked correct")
        return self


class AdminQuestionIds(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1)


class AdminBulkPatch(BaseModel):
    """Set a category and/or difficulty across many questions at once."""

    ids: list[uuid.UUID] = Field(min_length=1)
    category: str | None = Field(default=None, min_length=1, max_length=50)
    difficulty: Difficulty | None = None

    @model_validator(mode="after")
    def at_least_one_change(self) -> "AdminBulkPatch":
        if self.category is None and self.difficulty is None:
            raise ValueError("provide a category, a difficulty, or both")
        return self


class AdminBulkResult(BaseModel):
    affected: int
