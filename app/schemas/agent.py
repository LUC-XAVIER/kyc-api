"""Schemas for MFI agent (dashboard staff) management."""

import uuid

from pydantic import BaseModel, Field

from app.models.enums import AgentRole, AgentStatus

# PIN is the shared 6-8 character credential (see Agent.hashed_pin).
Pin = Field(min_length=6, max_length=8)


class AgentCreate(BaseModel):
    """Fields a manager supplies to provision a new field agent.

    Agents sign in by phone (no email); the manager sets the initial PIN.
    """

    full_name: str
    phone: str
    pin: str = Pin
    branch: str | None = None


class AgentUpdate(BaseModel):
    """Mutable fields on an existing agent (all optional / partial)."""

    full_name: str | None = None
    branch: str | None = None
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
    branch: str | None
    role: AgentRole
    status: AgentStatus
