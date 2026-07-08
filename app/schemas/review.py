"""Request/response schemas for the manager review queue."""

import enum
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import VerificationStatus


class ReviewItem(BaseModel):
    """A PENDING verification awaiting a manager decision."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: str
    status: VerificationStatus
    reject_reason: str | None
    confidence_score: float | None
    created_at: datetime


class ReviewAction(enum.StrEnum):
    """The manager's decision on a reviewed verification."""

    APPROVE = "approve"
    REJECT = "reject"


class ReviewDecisionRequest(BaseModel):
    """Manager decision on a PENDING verification."""

    action: ReviewAction
    reason: str | None = Field(default=None, max_length=64)


class ReviewDecisionResponse(BaseModel):
    """Result of applying a review decision."""

    verification_id: uuid.UUID
    status: VerificationStatus
