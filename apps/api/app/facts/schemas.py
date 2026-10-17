"""Request and response shapes for the fact vault and answer bank (PLAN s7)."""

import re
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

ANSWER_KEY = re.compile(r"^[a-z][a-z0-9_]{0,63}$")
MAX_ANSWERS = 200
MAX_ANSWER_CHARS = 2000


class FactOut(BaseModel):
    id: str
    kind: str
    text: str
    structured: dict[str, Any]
    source: str
    source_ref: Optional[str] = None
    inferred: bool
    status: str
    conflict_with: Optional[str] = None
    conflict_with_text: Optional[str] = None
    confirmed_at: Optional[datetime] = None


class ResumeUploadResponse(BaseModel):
    upload_id: str
    sha256: str
    text_source: str  # "text_layer" | "pdf_document"
    proposals: list[FactOut]
    skipped_duplicates: int
    contains_instructions: bool
    # Already approved, but not in this resume: kept, listed so the user can drop any.
    kept_from_before: list[FactOut] = []


class FactIdsRequest(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=500)


class FactCreate(BaseModel):
    """A fact the user adds by hand: approved at once, because they are its source."""

    kind: str
    text: str = Field(min_length=1, max_length=500)
    # Optional fields, e.g. company and title so an achievement lands under that role.
    structured: dict[str, Optional[str]] = Field(default_factory=dict)


class FactUpdate(BaseModel):
    text: Optional[str] = Field(default=None, min_length=1, max_length=500)
    structured: Optional[dict[str, Optional[str]]] = None


class FactBatchResponse(BaseModel):
    facts: list[FactOut]


class ProfileResponse(BaseModel):
    profile: dict[str, Any]
    pending_proposals: list[FactOut]
    updated_at: Optional[datetime] = None


class AnswerBank(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)

    @field_validator("answers")
    @classmethod
    def _check(cls, answers: dict[str, str]) -> dict[str, str]:
        if len(answers) > MAX_ANSWERS:
            raise ValueError(f"At most {MAX_ANSWERS} answers.")
        for key, value in answers.items():
            if not ANSWER_KEY.match(key):
                raise ValueError(f"Invalid answer key {key!r}: use lower_snake_case, max 64 chars.")
            if len(value) > MAX_ANSWER_CHARS:
                raise ValueError(f"Answer {key!r} is longer than {MAX_ANSWER_CHARS} characters.")
        return answers


class AnswerBankResponse(AnswerBank):
    updated_at: Optional[datetime] = None


class AnswerMemoryOut(BaseModel):
    id: int
    question: str
    answer: str
    uses: int = 0
    updated_at: Optional[datetime] = None


class AnswerMemoryUpdate(BaseModel):
    answer: str = Field(min_length=1, max_length=MAX_ANSWER_CHARS)
