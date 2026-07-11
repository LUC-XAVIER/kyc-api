"""Schemas for MFI agent (dashboard staff) management."""

import uuid

from pydantic import BaseModel

from app.models.enums import AgentRole, AgentStatus


class AgentCreate(BaseModel):
    """Fields a manager supplies to provision a new dashboard agent."""

    full_name: str
    email: str
    password: str
    branch: str | None = None
    role: AgentRole = AgentRole.AGENT


class AgentUpdate(BaseModel):
    """Mutable fields on an existing agent (all optional / partial)."""

    full_name: str | None = None
    branch: str | None = None
    role: AgentRole | None = None
    status: AgentStatus | None = None


class AgentSummary(BaseModel):
    """Public view of an agent (never exposes the password hash)."""

    id: uuid.UUID
    full_name: str
    email: str | None
    branch: str | None
    role: AgentRole
    status: AgentStatus
