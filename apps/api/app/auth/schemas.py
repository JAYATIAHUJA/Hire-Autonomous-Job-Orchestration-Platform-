"""Request and response shapes for /v1/auth and /v1/me."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class EmailRequest(BaseModel):
    email: str = Field(..., max_length=320)


class OtpVerifyRequest(BaseModel):
    email: str = Field(..., max_length=320)
    code: str = Field(..., max_length=12)


class OtpSendResponse(BaseModel):
    sent: bool = True
    expires_in_seconds: int


class MeOut(BaseModel):
    id: int
    email: Optional[str] = None
    display_name: Optional[str] = None
    role: str
    created_at: Optional[datetime] = None
    providers: list[str] = []
