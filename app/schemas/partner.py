"""Response schemas for the standalone partner verification endpoint.

The partner integrates KYC into its own system, so it gets the full per-stage
breakdown (OCR fields, liveness, face match) rather than the trimmed,
quota-oriented shape MFIs receive. There is no request model: the endpoint
takes multipart form-data (image uploads + fields), read via ``UploadFile`` /
``Form`` in the route.

These models validate straight from the pipeline's frozen dataclasses
(``OcrResult`` / ``LivenessOutcome`` / ``FaceMatchOutcome``) via
``from_attributes``; the field names line up one-to-one on purpose.
"""

from datetime import date

from pydantic import BaseModel, ConfigDict

from app.models.enums import Sex, VerificationStatus


class PartnerOcr(BaseModel):
    """OCR fields read off the document (identity data — HTTPS only)."""

    model_config = ConfigDict(from_attributes=True)

    full_name: str | None
    id_number: str | None
    date_of_birth: date | None
    place_of_birth: str | None
    expiry_date: date | None
    sex: Sex | None
    occupation: str | None
    field_confidences: dict[str, float] | None


class PartnerLiveness(BaseModel):
    """Liveness / anti-spoof outcome for the selfie."""

    model_config = ConfigDict(from_attributes=True)

    passed: bool
    score: float
    method: str


class PartnerFaceMatch(BaseModel):
    """Selfie-vs-portrait similarity outcome."""

    model_config = ConfigDict(from_attributes=True)

    match_score: float
    verified: bool
    threshold: float


class PartnerVerifyResponse(BaseModel):
    """Full result of a stateless partner verification.

    ``reference`` echoes the caller's own correlation id (if they sent one)
    so they can tie the response to their request; nothing is stored on our
    side. Per-stage fields are populated only for the stages that ran — a
    stage skipped by the pipeline's early-exit comes back ``null``.
    """

    reference: str
    status: VerificationStatus
    confidence_score: float | None
    reject_reason: str | None
    extracted_data: PartnerOcr | None
    liveness: PartnerLiveness | None
    face_match: PartnerFaceMatch | None
