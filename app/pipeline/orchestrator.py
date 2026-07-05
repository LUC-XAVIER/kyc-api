"""Verification pipeline orchestrator.

:func:`run_verification` composes the stages in Design doc §6.3.1 order —
preprocess → OCR → liveness → face match → duplicate → decision — with
early exit: a failing stage returns immediately so the expensive face
stages never run after an OCR or liveness failure. The verdict comes from
:func:`app.pipeline.decision.decide`; OCR failure and expiry are handled
inline (they precede the stages ``decide`` knows about).

The duplicate search and embedding persistence go through the
:class:`DuplicateStore` port, so the orchestration is unit-testable with a
fake store and carries no database dependency itself.

:func:`run_pipeline` remains the Phase 2 stub the API calls until the
verify endpoint accepts multipart image uploads (Phase 3).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Protocol

from app.models.enums import VerificationStatus
from app.pipeline.contracts import Decision, PipelineInput, RejectReason
from app.pipeline.decision import decide
from app.pipeline.stages.duplicate import FaceIndex
from app.pipeline.stages.face_match import match_embeddings, represent_face
from app.pipeline.stages.liveness import check_liveness
from app.pipeline.stages.ocr import ocr_extract
from app.pipeline.stages.preprocess import crop_nic_zones, preprocess_image

if TYPE_CHECKING:
    import numpy as np


@dataclass(frozen=True)
class PipelineResult:
    """Outcome of running the verification pipeline.

    Attributes:
        status: The decision (VERIFIED / PENDING / REJECTED).
        confidence: Overall confidence in ``[0, 1]``, if applicable.
        reject_reason: Short machine-readable reason when REJECTED.
    """

    status: VerificationStatus
    confidence: float | None = None
    reject_reason: str | None = None


class DuplicateStore(Protocol):
    """Persistence port for duplicate-face search and enrollment.

    Backed in production by the pgvector ``FaceEmbedding`` table, scoped to
    one MFI account.
    """

    def build_index(
        self, mfi_account_id: uuid.UUID, *, exclude_client_id: str
    ) -> FaceIndex:
        """Return a search index of the MFI's other clients' embeddings."""
        ...

    def add_embedding(
        self, mfi_account_id: uuid.UUID, client_id: str, embedding: np.ndarray
    ) -> None:
        """Enroll a verified client's embedding for future searches."""
        ...


def run_verification(
    data: PipelineInput, *, duplicate_store: DuplicateStore
) -> PipelineResult:
    """Run the full verification pipeline for one client.

    Args:
        data: The images, document type, and tenant/client references.
        duplicate_store: Port for duplicate search and embedding enrollment.

    Returns:
        The pipeline's :class:`PipelineResult`.
    """
    front = preprocess_image(data.id_front_image)
    selfie = preprocess_image(data.selfie_image)
    back = (
        preprocess_image(data.id_back_image)
        if data.id_back_image is not None
        else None
    )
    zones = crop_nic_zones(front)

    # Step 2 — OCR (and its two inline rejects, ahead of the face stages).
    ocr = ocr_extract(zones.text_zone, data.document_type, back_image=back)
    if not ocr.success:
        return _rejected(RejectReason.OCR_FAILED)
    if ocr.expiry_date is not None and ocr.expiry_date < date.today():
        return _rejected(RejectReason.ID_EXPIRED)

    # Step 3 — Liveness. A failure short-circuits the expensive face stages.
    liveness = check_liveness(selfie)
    if not liveness.passed:
        return _to_result(decide(liveness))

    # Step 4 — Face match. Embed the selfie once and reuse it for Step 5.
    selfie_embedding = represent_face(selfie)
    face = match_embeddings(selfie_embedding, represent_face(zones.photo_zone))
    if not face.verified:
        return _to_result(decide(liveness, face))

    # Step 5 — Duplicate search against the MFI's other clients.
    index = duplicate_store.build_index(
        data.mfi_account_id, exclude_client_id=data.client_id
    )
    duplicate = index.search(selfie_embedding)

    # Step 6 — Decide; enroll the embedding only on a clean pass.
    decision = decide(liveness, face, duplicate)
    if decision.status is VerificationStatus.VERIFIED:
        duplicate_store.add_embedding(
            data.mfi_account_id, data.client_id, selfie_embedding
        )
    return _to_result(decision)


def _rejected(reason: str) -> PipelineResult:
    """A REJECTED result carrying ``reason``."""
    return PipelineResult(
        status=VerificationStatus.REJECTED, reject_reason=reason
    )


def _to_result(decision: Decision) -> PipelineResult:
    """Map a decision-engine :class:`Decision` onto a pipeline result."""
    return PipelineResult(
        status=decision.status,
        confidence=decision.confidence,
        reject_reason=decision.reject_reason,
    )


def run_pipeline(*, client_id: str) -> PipelineResult:
    """Run the verification pipeline for one client.

    Args:
        client_id: The MFI-scoped client reference under verification.

    Returns:
        The pipeline's :class:`PipelineResult`.
    """
    # STUB (Phase 2): always succeeds. The verify endpoint switches to
    # run_verification once it accepts multipart image uploads (Phase 3).
    return PipelineResult(status=VerificationStatus.VERIFIED, confidence=0.99)
