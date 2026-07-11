"""Schemas for MFI API-key management."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class ApiKeySummary(BaseModel):
    """Non-secret view of an API key (only its prefix is ever shown)."""

    id: uuid.UUID
    prefix: str
    is_active: bool
    created_at: datetime
    last_used_at: datetime | None


class ApiKeyCreated(BaseModel):
    """A freshly minted key — the one and only time the secret is shown."""

    id: uuid.UUID
    prefix: str
    full_key: str
    created_at: datetime
