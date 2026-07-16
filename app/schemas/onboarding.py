"""Schemas for self-service manager onboarding."""

from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from app.core.validation import normalize_cm_phone

_Pin = Field(min_length=6, max_length=8)
_Phone = Annotated[str, AfterValidator(normalize_cm_phone)]


class OnboardingStart(BaseModel):
    """Landing-page request: the customer's email and chosen plan."""

    email: str
    plan: str


class StartResponse(BaseModel):
    """Acknowledgement. ``signup_link`` is only set in dev (email off)."""

    status: str = "sent"
    signup_link: str | None = None


class InviteInfo(BaseModel):
    """The invite behind a signup token (email pre-fills the form)."""

    email: str
    plan: str


class OnboardingComplete(BaseModel):
    """The manager's details posted from the signup form."""

    token: str
    full_name: str
    mfi_name: str
    pin: str = _Pin
    phone: _Phone | None = None


class CompleteResponse(BaseModel):
    """Result of a completed signup."""

    status: str = "created"
    email: str
