import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class UserPublic(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    username: str
    email: str
    created_at: datetime
    updated_at: datetime


class UserUpdate(BaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=50)
    email: str | None = Field(default=None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def at_least_one_field(self) -> "UserUpdate":
        if self.username is None and self.email is None:
            raise ValueError("at least one field must be provided")
        return self
