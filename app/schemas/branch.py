"""Schemas for MFI branch (office/location) management."""

import uuid

from pydantic import BaseModel


class BranchCreate(BaseModel):
    """A manager creating a new branch/office."""

    name: str


class BranchSummary(BaseModel):
    """Public view of a branch."""

    id: uuid.UUID
    name: str
