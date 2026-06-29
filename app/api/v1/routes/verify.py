"""KYC verification endpoint.

Authenticates the caller, enforces the monthly quota, runs the (stubbed)
verification pipeline, persists the result, and consumes one unit of quota.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_metered_mfi
from app.db.session import get_db
from app.models import MfiAccount, Verification
from app.models.enums import SubmissionMethod
from app.pipeline.orchestrator import run_pipeline
from app.schemas.verification import VerifyRequest, VerifyResponse
from app.services import subscription

router = APIRouter(prefix="/kyc", tags=["verification"])


@router.post(
    "/verify",
    response_model=VerifyResponse,
    status_code=status.HTTP_201_CREATED,
)
def verify(
    payload: VerifyRequest,
    mfi: MfiAccount = Depends(get_metered_mfi),
    db: Session = Depends(get_db),
) -> VerifyResponse:
    """Run a verification for the authenticated MFI and record it.

    Quota is checked before the pipeline runs (via the dependency) and one
    unit is consumed only once a verification has been processed.
    """
    result = run_pipeline(client_id=payload.client_id)

    verification = Verification(
        client_id=payload.client_id,
        mfi_account_id=mfi.id,
        submission_method=SubmissionMethod.API,
        status=result.status,
        confidence_score=result.confidence,
        reject_reason=result.reject_reason,
        processed_at=datetime.now(UTC),
    )
    db.add(verification)
    subscription.record_usage(db, mfi)
    db.refresh(verification)

    quota = subscription.get_quota_status(mfi)
    return VerifyResponse(
        verification_id=verification.id,
        client_id=verification.client_id,
        status=verification.status,
        confidence_score=verification.confidence_score,
        reject_reason=verification.reject_reason,
        quota_remaining=quota.remaining,
        quota_warning=quota.warning,
    )
