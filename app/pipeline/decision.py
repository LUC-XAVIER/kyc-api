"""Decision engine — combine stage outcomes into a final verdict.

Implements the priority order of Design doc §6.3.1: a failed liveness check
rejects outright, then a failed face match, then a positive duplicate hit
sends the case to manual review (PENDING); otherwise the verification is
VERIFIED. The function is tolerant of ``None`` for stages that were skipped
by the orchestrator's early-exit, so it stays the single source of truth
for the verdict without forcing every stage to run.
"""

from app.models.enums import VerificationStatus
from app.pipeline.contracts import (
    Decision,
    DuplicateOutcome,
    FaceMatchOutcome,
    LivenessOutcome,
    RejectReason,
)

# Relative weights when blending stage scores into one confidence figure.
# Tunable; face similarity is weighted slightly higher than liveness.
_LIVENESS_WEIGHT = 0.4
_FACE_WEIGHT = 0.6


def _blend_confidence(
    liveness: LivenessOutcome, face_match: FaceMatchOutcome
) -> float:
    """Blend liveness and face-match scores into a single confidence."""
    score = (
        _LIVENESS_WEIGHT * liveness.score
        + _FACE_WEIGHT * face_match.match_score
    )
    return round(score, 4)


def decide(
    liveness: LivenessOutcome,
    face_match: FaceMatchOutcome | None = None,
    duplicate: DuplicateOutcome | None = None,
) -> Decision:
    """Return the final verdict from the available stage outcomes.

    Args:
        liveness: Always required; evaluated first.
        face_match: Required to reach VERIFIED/PENDING; ``None`` if the
            orchestrator exited after a failed liveness check.
        duplicate: Optional; ``None`` if not run.

    Returns:
        The resulting :class:`Decision`.
    """
    if not liveness.passed:
        return Decision(
            status=VerificationStatus.REJECTED,
            confidence=liveness.score,
            reject_reason=RejectReason.LIVENESS_FAILED,
        )

    if face_match is not None and not face_match.verified:
        return Decision(
            status=VerificationStatus.REJECTED,
            confidence=face_match.match_score,
            reject_reason=RejectReason.FACE_MISMATCH,
        )

    if duplicate is not None and duplicate.is_duplicate:
        return Decision(
            status=VerificationStatus.PENDING,
            confidence=face_match.match_score if face_match else None,
        )

    return Decision(
        status=VerificationStatus.VERIFIED,
        confidence=_blend_confidence(liveness, face_match)
        if face_match
        else None,
    )
