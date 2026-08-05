"""Response schemas for account / subscription endpoints."""

import uuid

from pydantic import BaseModel

from app.models.enums import MfiStatus


class AccountSummary(BaseModel):
    """Public summary of an authenticated MFI account and its quota."""

    id: uuid.UUID
    name: str
    email: str
    # PENDING until the first payment activates the subscription; the
    # dashboard shows a pay-to-activate gate while it is not ACTIVE.
    status: MfiStatus
    plan_name: str | None
    verification_quota: int | None
    current_period_usage: int
    # Email-notification toggles (quota / pending / weekly / maintenance),
    # always fully populated (defaults filled server-side).
    notification_prefs: dict[str, bool]


class AccountUpdate(BaseModel):
    """Editable MFI-profile fields (manager Settings)."""

    name: str | None = None
    email: str | None = None
    # Partial map of notification toggles to update; unknown keys ignored.
    notification_prefs: dict[str, bool] | None = None
