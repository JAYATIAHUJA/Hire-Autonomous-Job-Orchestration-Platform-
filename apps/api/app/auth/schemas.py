"""Request and response shapes for /v1/auth and /v1/me."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class EmailRequest(BaseModel):
    email: str = Field(..., max_length=320)


class OtpVerifyRequest(BaseModel):
    email: str = Field(..., max_length=320)
    code: str = Field(..., max_length=12)


class OtpSendResponse(BaseModel):
    sent: bool = True
    expires_in_seconds: int


class ConsentPurposes(BaseModel):
    """One switch per optional purpose. Each starts off: consent is an affirmative act."""

    github: bool = False
    resume: bool = False
    email: bool = False


class ConsentRequest(BaseModel):
    notice_version: str = Field(..., min_length=1, max_length=32)
    notice_hash: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    purposes: ConsentPurposes


class ConsentOut(ConsentRequest):
    accepted_at: datetime


class MeOut(BaseModel):
    id: int
    email: Optional[str] = None
    display_name: Optional[str] = None
    role: str
    created_at: Optional[datetime] = None
    providers: list[str] = []
    # Same list as ``providers``, under the name the web client uses.
    identities: list[str] = []
    consent: Optional[ConsentOut] = None
    onboarding_completed_at: Optional[datetime] = None


class MePatch(BaseModel):
    display_name: Optional[str] = Field(default=None, max_length=120)
    # Only ``true`` is meaningful: onboarding is finished once and stays finished.
    onboarding_completed: Optional[bool] = None


class SalaryFloor(BaseModel):
    amount: int = Field(..., ge=0, le=10**9)
    currency: Literal["INR", "USD"]
    period: Literal["year"] = "year"


class Preferences(BaseModel):
    roles: list[str] = Field(default_factory=list, max_length=20)
    locations: list[str] = Field(default_factory=list, max_length=20)
    remote_ok: bool = False
    experience_band: Optional[Literal["0-1", "1-3", "3-5", "5-8", "8-12", "12+"]] = None
    salary_floor: Optional[SalaryFloor] = None
    deal_breakers: list[str] = Field(default_factory=list, max_length=20)

    @field_validator("roles", "locations", "deal_breakers")
    @classmethod
    def _short_items(cls, items: list[str]) -> list[str]:
        cleaned = [i.strip() for i in items if i and i.strip()]
        if any(len(i) > 100 for i in cleaned):
            raise ValueError("Each item must be at most 100 characters.")
        return cleaned
