"""Request/response schemas for the verification endpoint."""

import uuid

from pydantic import BaseModel, Field

from app.models.enums import VerificationStatus


class VerifyRequest(BaseModel):
    """Inbound payload for a verification request.

    Phase 2 only needs a client reference for the stub pipeline. The ID
    document and selfie images arrive as multipart uploads in Phase 3.
    """

    client_id: str = Field(min_length=1, max_length=64)


class VerifyResponse(BaseModel):
    """Result of a verification, plus the caller's live quota state."""

    verification_id: uuid.UUID
    client_id: str
    status: VerificationStatus
    confidence_score: float | None
    reject_reason: str | None
    quota_remaining: int
    quota_warning: bool
