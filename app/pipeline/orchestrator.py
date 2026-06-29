"""Verification pipeline orchestrator.

Phase 2 ships a **stub** that returns a canned VERIFIED decision so the API
and quota flow are demoable end to end. The real pipeline (preprocess → OCR
→ liveness → face match → duplicate → decision, with early-exit per Design
doc §6.3.1) replaces :func:`run_pipeline`'s body in Phase 3 without changing
its signature.
"""

from dataclasses import dataclass

from app.models.enums import VerificationStatus


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


def run_pipeline(*, client_id: str) -> PipelineResult:
    """Run the verification pipeline for one client.

    Args:
        client_id: The MFI-scoped client reference under verification.

    Returns:
        The pipeline's :class:`PipelineResult`.
    """
    # STUB (Phase 2): always succeeds. Replaced by the real ML pipeline in
    # Phase 3 — preprocess, OCR, liveness, face match, duplicate, decision.
    return PipelineResult(status=VerificationStatus.VERIFIED, confidence=0.99)
