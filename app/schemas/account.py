"""Response schemas for account / subscription endpoints."""

import uuid

from pydantic import BaseModel


class AccountSummary(BaseModel):
    """Public summary of an authenticated MFI account and its quota."""

    id: uuid.UUID
    name: str
    email: str
    plan_name: str | None
    verification_quota: int | None
    current_period_usage: int


class AccountUpdate(BaseModel):
    """Editable MFI-profile fields (manager Settings)."""

    name: str | None = None
    email: str | None = None
