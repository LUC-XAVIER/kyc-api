"""Data contracts shared across verification pipeline stages.

Every stage consumes the :class:`PipelineInput` (or part of it) and returns
its own frozen outcome. The decision engine (``app.pipeline.decision``)
combines the outcomes into a final :class:`Decision`. Keeping these as
plain dataclasses — with no ML imports — lets the orchestrator, the
decision engine, and their tests run without the heavy ``ml`` extra.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date

from app.models.enums import Sex, VerificationStatus


class RejectReason:
    """Machine-readable reject codes stored on ``Verification``."""

    OCR_FAILED = "OCR_FAILED"
    LIVENESS_FAILED = "LIVENESS_FAILED"
    FACE_MISMATCH = "FACE_MISMATCH"


@dataclass(frozen=True)
class PipelineInput:
    """Everything a verification needs to run end to end.

    Attributes:
        client_id: MFI-scoped client reference under verification.
        mfi_account_id: Owning tenant, used to scope duplicate search.
        id_image: Raw bytes of the national ID document image.
        selfie_image: Raw bytes of the live selfie capture.
    """

    client_id: str
    mfi_account_id: uuid.UUID
    id_image: bytes
    selfie_image: bytes


@dataclass(frozen=True)
class OcrResult:
    """Fields extracted from the national ID card by OCR."""

    success: bool
    full_name: str | None = None
    id_number: str | None = None
    date_of_birth: date | None = None
    place_of_birth: str | None = None
    expiry_date: date | None = None
    sex: Sex | None = None
    field_confidences: dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class LivenessOutcome:
    """Result of the liveness / anti-spoofing check on the selfie."""

    passed: bool
    score: float
    method: str


@dataclass(frozen=True)
class FaceMatchOutcome:
    """Similarity between the selfie and the ID-card portrait."""

    match_score: float
    verified: bool
    threshold: float


@dataclass(frozen=True)
class DuplicateOutcome:
    """Whether this face already exists for another client."""

    is_duplicate: bool
    similarity: float
    matched_client_id: str | None = None


@dataclass(frozen=True)
class Decision:
    """Final verdict produced by the decision engine."""

    status: VerificationStatus
    confidence: float | None = None
    reject_reason: str | None = None
