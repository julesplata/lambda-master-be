import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Difficulty = Literal["easy", "medium", "hard"]


class QuestionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    difficulty: Difficulty


class OptionPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    text: str


class QuestionDetail(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    difficulty: Difficulty
    options: list[OptionPublic]


class OptionCreate(BaseModel):
    text: str = Field(min_length=1)
    is_correct: bool = False


class QuestionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    difficulty: Difficulty
    explanation: str | None = None
    options: list[OptionCreate] = Field(min_length=2)
    tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def at_least_one_correct(self) -> "QuestionCreate":
        if not any(option.is_correct for option in self.options):
            raise ValueError("at least one option must be marked correct")
        return self


class BulkQuestionCreate(BaseModel):
    questions: list[QuestionCreate] = Field(min_length=1)


class BulkCreateResponse(BaseModel):
    created: int
    question_ids: list[uuid.UUID]
