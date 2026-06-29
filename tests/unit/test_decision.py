"""Unit tests for the pipeline decision engine (§6.3.1 verdict rules)."""

from app.models.enums import VerificationStatus
from app.pipeline.contracts import (
    DuplicateOutcome,
    FaceMatchOutcome,
    LivenessOutcome,
    RejectReason,
)
from app.pipeline.decision import decide

_LIVE_PASS = LivenessOutcome(passed=True, score=0.95, method="lbp-svm")
_LIVE_FAIL = LivenessOutcome(passed=False, score=0.20, method="lbp-svm")
_FACE_PASS = FaceMatchOutcome(match_score=0.82, verified=True, threshold=0.40)
_FACE_FAIL = FaceMatchOutcome(match_score=0.10, verified=False, threshold=0.40)
_DUP_HIT = DuplicateOutcome(
    is_duplicate=True, similarity=0.91, matched_client_id="C-9"
)
_DUP_CLEAR = DuplicateOutcome(is_duplicate=False, similarity=0.10)


def test_failed_liveness_rejects_first() -> None:
    """A spoofed selfie is rejected before any other stage matters."""
    decision = decide(_LIVE_FAIL, _FACE_PASS, _DUP_CLEAR)
    assert decision.status == VerificationStatus.REJECTED
    assert decision.reject_reason == RejectReason.LIVENESS_FAILED


def test_failed_liveness_without_later_stages() -> None:
    """Liveness alone is enough to reject (early-exit path)."""
    decision = decide(_LIVE_FAIL)
    assert decision.status == VerificationStatus.REJECTED
    assert decision.reject_reason == RejectReason.LIVENESS_FAILED


def test_failed_face_match_rejects() -> None:
    """Live but mismatched face is rejected for FACE_MISMATCH."""
    decision = decide(_LIVE_PASS, _FACE_FAIL)
    assert decision.status == VerificationStatus.REJECTED
    assert decision.reject_reason == RejectReason.FACE_MISMATCH


def test_duplicate_sends_to_manual_review() -> None:
    """A passing verification with a duplicate hit becomes PENDING."""
    decision = decide(_LIVE_PASS, _FACE_PASS, _DUP_HIT)
    assert decision.status == VerificationStatus.PENDING
    assert decision.reject_reason is None
    assert decision.confidence == _FACE_PASS.match_score


def test_all_clear_is_verified_with_blended_confidence() -> None:
    """All stages pass -> VERIFIED with a blended confidence in [0, 1]."""
    decision = decide(_LIVE_PASS, _FACE_PASS, _DUP_CLEAR)
    assert decision.status == VerificationStatus.VERIFIED
    assert decision.reject_reason is None
    assert 0.0 <= decision.confidence <= 1.0
    # 0.4*0.95 + 0.6*0.82 = 0.872
    assert decision.confidence == 0.872


def test_verified_when_duplicate_stage_skipped() -> None:
    """Liveness + face passing with no duplicate stage still verifies."""
    decision = decide(_LIVE_PASS, _FACE_PASS)
    assert decision.status == VerificationStatus.VERIFIED
