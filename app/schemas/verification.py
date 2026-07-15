"""Request/response schemas for the verification endpoints.

The verify request arrives as multipart form-data (image uploads + fields),
which FastAPI reads via ``UploadFile``/``Form`` in the route, so there is no
request body model here — only responses, including the read-back detail a
manager sees when reviewing a case.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import (
    DuplicateResolution,
    Sex,
    SubmissionMethod,
    VerificationStatus,
)


class VerifyResponse(BaseModel):
    """Result of a verification, plus the caller's live quota state."""

    verification_id: uuid.UUID
    client_id: str
    status: VerificationStatus
    confidence_score: float | None
    reject_reason: str | None
    quota_remaining: int
    quota_warning: bool


class VerificationSummary(BaseModel):
    """One row in a verification list."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: str
    client_name: str | None
    status: VerificationStatus
    reject_reason: str | None
    confidence_score: float | None
    submission_method: SubmissionMethod
    agent_name: str | None
    branch_name: str | None
    created_at: datetime


class ExtractedDataSchema(BaseModel):
    """OCR fields read from the document."""

    model_config = ConfigDict(from_attributes=True)

    full_name: str | None
    id_number: str | None
    date_of_birth: date | None
    place_of_birth: str | None
    expiry_date: date | None
    sex: Sex | None
    occupation: str | None
    field_confidences: dict | None


class LivenessResultSchema(BaseModel):
    """Anti-spoofing result."""

    model_config = ConfigDict(from_attributes=True)

    passed: bool
    method: str
    anti_spoof_score: float | None
    landmarks_detected: bool


class FaceMatchResultSchema(BaseModel):
    """Selfie-vs-portrait match result."""

    model_config = ConfigDict(from_attributes=True)

    match_score: float
    verified: bool
    threshold: float


class DuplicateFlagSchema(BaseModel):
    """A duplicate hit and its review resolution."""

    model_config = ConfigDict(from_attributes=True)

    matched_client_id: str | None
    similarity_score: float
    resolution: DuplicateResolution


class VerificationDetail(VerificationSummary):
    """A verification with its per-stage records, for manual review."""

    processed_at: datetime | None
    extracted_data: ExtractedDataSchema | None
    liveness_result: LivenessResultSchema | None
    face_match_result: FaceMatchResultSchema | None
    duplicate_flags: list[DuplicateFlagSchema]
