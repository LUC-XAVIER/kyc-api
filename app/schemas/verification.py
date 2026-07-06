"""Request/response schemas for the verification endpoint.

The request arrives as multipart form-data (image uploads + fields), which
FastAPI reads via ``UploadFile``/``Form`` in the route, so there is no
request body model here — only the response.
"""

import uuid

from pydantic import BaseModel

from app.models.enums import VerificationStatus


class VerifyResponse(BaseModel):
    """Result of a verification, plus the caller's live quota state."""

    verification_id: uuid.UUID
    client_id: str
    status: VerificationStatus
    confidence_score: float | None
    reject_reason: str | None
    quota_remaining: int
    quota_warning: bool
