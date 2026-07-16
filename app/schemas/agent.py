"""Schemas for MFI agent (dashboard staff) management."""

import uuid
from typing import Annotated

from pydantic import AfterValidator, BaseModel, Field

from app.core.validation import normalize_cm_phone
from app.models.enums import AgentRole, AgentStatus

# PIN is the shared 6-8 character credential (see User.hashed_pin).
Pin = Field(min_length=6, max_length=8)
# A Cameroonian phone, normalized to +237 + 9 digits.
Phone = Annotated[str, AfterValidator(normalize_cm_phone)]


class AgentCreate(BaseModel):
    """Fields a manager supplies to provision a new field agent.

    Agents sign in by phone (no email); the manager sets the initial PIN.
    """

    full_name: str
    phone: Phone
    pin: str = Pin
    branch_id: uuid.UUID


class AgentUpdate(BaseModel):
    """Mutable fields on an existing agent (all optional / partial)."""

    full_name: str | None = None
    branch_id: uuid.UUID | None = None
    status: AgentStatus | None = None


class AgentPinReset(BaseModel):
    """A manager re-initialising an agent's PIN (agent forgot theirs)."""

    pin: str = Pin


class AgentSummary(BaseModel):
    """Public view of an agent (never exposes the PIN hash)."""

    id: uuid.UUID
    full_name: str
    email: str | None
    phone: str | None
    branch_id: uuid.UUID | None
    branch_name: str | None
    role: AgentRole
    status: AgentStatus
