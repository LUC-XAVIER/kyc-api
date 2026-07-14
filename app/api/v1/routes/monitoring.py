"""Model-drift monitoring endpoints for the authenticated MFI.

Compares the MFI's recent face-match scores (the current window) against the
immediately preceding window of equal length and reports whether the score
distribution has drifted.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.v1.deps import Principal, require_manager_principal
from app.db.session import get_db
from app.schemas.monitoring import DriftReport
from app.services import monitoring

router = APIRouter(prefix="/kyc/monitoring", tags=["monitoring"])


@router.get("/drift", response_model=DriftReport)
def face_match_drift(
    window_days: int = Query(default=30, ge=1, le=365),
    principal: Principal = Depends(require_manager_principal),
    db: Session = Depends(get_db),
) -> DriftReport:
    """Report face-match score drift: last ``window_days`` vs the prior one."""
    now = datetime.now(UTC)
    current_start = now - timedelta(days=window_days)
    reference_start = now - timedelta(days=2 * window_days)
    mfi_id = principal.mfi_account.id

    reference = monitoring.face_match_scores(
        db, mfi_id, since=reference_start, until=current_start
    )
    current = monitoring.face_match_scores(
        db, mfi_id, since=current_start, until=now
    )

    if (
        len(reference) < monitoring.MIN_SAMPLES
        or len(current) < monitoring.MIN_SAMPLES
    ):
        return DriftReport(
            method=None,
            drift_score=None,
            drift_detected=False,
            reference_size=len(reference),
            current_size=len(current),
            sufficient_data=False,
        )

    outcome = monitoring.detect_drift(reference, current)
    return DriftReport(
        method=outcome.method,
        drift_score=outcome.drift_score,
        drift_detected=outcome.drift_detected,
        reference_size=len(reference),
        current_size=len(current),
        sufficient_data=True,
    )
