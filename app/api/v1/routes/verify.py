"""KYC verification endpoint.

Authenticates the caller, enforces the monthly quota, runs the verification
pipeline over the uploaded images, persists the result and enrolled
embedding, and consumes one unit of quota.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, UploadFile, status
from sqlalchemy.orm import Session

from app.api.v1.deps import get_metered_mfi
from app.core.exceptions import ValidationError
from app.db.session import get_db
from app.models import FaceEmbedding, MfiAccount, Verification
from app.models.enums import DocumentType, SubmissionMethod
from app.pipeline.contracts import PipelineInput
from app.pipeline.orchestrator import run_verification
from app.schemas.verification import VerifyResponse
from app.services import subscription
from app.services.duplicate_store import PgVectorDuplicateStore

router = APIRouter(prefix="/kyc", tags=["verification"])


def build_pipeline_input(
    *,
    client_id: str,
    mfi_account_id: uuid.UUID,
    document_type: DocumentType,
    id_front: bytes,
    selfie: bytes,
    id_back: bytes | None = None,
) -> PipelineInput:
    """Validate the uploaded pieces and assemble a :class:`PipelineInput`.

    Enforces the document-type rule the frozen contract can't express: a NIC
    is two-sided (expiry, ID number, or place of birth live on the back), so
    it requires ``id_back``; a single-page passport does not.

    Raises:
        ValidationError: If a required image is empty, or a NIC is missing
            its back image.
    """
    if not id_front or not selfie:
        raise ValidationError("The ID front and selfie images are required.")
    if document_type is DocumentType.NIC and not id_back:
        raise ValidationError("A NIC verification requires the card's back.")
    return PipelineInput(
        client_id=client_id,
        mfi_account_id=mfi_account_id,
        document_type=document_type,
        id_front_image=id_front,
        selfie_image=selfie,
        id_back_image=id_back,
    )


@router.post(
    "/verify",
    response_model=VerifyResponse,
    status_code=status.HTTP_201_CREATED,
)
def verify(
    client_id: str = Form(..., min_length=1, max_length=64),
    document_type: DocumentType = Form(...),
    id_front: UploadFile = File(...),
    selfie: UploadFile = File(...),
    id_back: UploadFile | None = File(None),
    mfi: MfiAccount = Depends(get_metered_mfi),
    db: Session = Depends(get_db),
) -> VerifyResponse:
    """Run a verification for the authenticated MFI and record it.

    Takes the ID images and selfie as multipart uploads. Quota is checked
    before the pipeline runs (via the dependency); the verification record,
    the enrolled embedding (on a clean pass), and one unit of usage are then
    persisted in the same transaction.
    """
    pipeline_input = build_pipeline_input(
        client_id=client_id,
        mfi_account_id=mfi.id,
        document_type=document_type,
        id_front=id_front.file.read(),
        selfie=selfie.file.read(),
        id_back=id_back.file.read() if id_back is not None else None,
    )
    output = run_verification(
        pipeline_input, duplicate_store=PgVectorDuplicateStore(db)
    )
    result = output.result

    verification = Verification(
        client_id=client_id,
        mfi_account_id=mfi.id,
        submission_method=SubmissionMethod.API,
        status=result.status,
        confidence_score=result.confidence,
        reject_reason=result.reject_reason,
        processed_at=datetime.now(UTC),
    )
    db.add(verification)
    db.flush()  # assign verification.id before the embedding references it
    if output.embedding is not None:
        db.add(
            FaceEmbedding(
                verification_id=verification.id,
                client_id=client_id,
                vector=output.embedding.tolist(),
                model_used="ArcFace",
            )
        )
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
