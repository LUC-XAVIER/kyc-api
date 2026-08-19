"""Standalone partner verification endpoint (stateless external API).

A single external enterprise embeds KYC into its own system and calls this
route directly. Unlike ``/kyc/verify`` it is **not** tied to an MFI: there is
no plan, no quota, no database write, and no duplicate detection — the
pipeline runs over the uploaded images and the full per-stage result is
returned, then nothing is kept.

Security (Design note): the caller authenticates with a single shared secret
in the ``X-API-Key`` header (``settings.partner_api_key``), compared in
constant time; the endpoint stays closed until that key is configured. A
per-key sliding-window rate limit stands in for the MFI quota, and each
uploaded image is size-capped before the pipeline runs. TLS (Caddy in prod)
keeps the images, the key, and the returned identity fields off the wire in
clear text.
"""

import hmac
import uuid

from fastapi import APIRouter, Depends, File, Form, Security, UploadFile
from fastapi.security import APIKeyHeader

from app.api.v1.routes.verify import build_pipeline_input
from app.core.config import settings
from app.core.exceptions import (
    AuthenticationError,
    PayloadTooLargeError,
    RateLimitedError,
)
from app.models.enums import DocumentType
from app.pipeline.contracts import DuplicateOutcome
from app.pipeline.orchestrator import run_verification
from app.schemas.partner import (
    PartnerFaceMatch,
    PartnerLiveness,
    PartnerOcr,
    PartnerVerifyResponse,
)
from app.services.rate_limit import SlidingWindowRateLimiter

router = APIRouter(prefix="/partner", tags=["partner"])

# Same header MFIs use; here it carries the single partner secret instead.
_partner_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

# Per-process throttle keyed by the presented key. One partner today, but
# keying by key keeps it correct if more are ever added.
_limiter = SlidingWindowRateLimiter(
    settings.partner_rate_limit_per_minute, window_seconds=60.0
)

# A verification the pipeline can't scope to a tenant still needs *some*
# client reference for its internal bookkeeping; the partner path enrolls
# nothing, so the value is inert.
_STATELESS_CLIENT_REF = "partner"
_STATELESS_TENANT_ID = uuid.UUID(int=0)


class _NoMatchIndex:
    """Duplicate index over an empty enrollment set: nothing ever matches."""

    def search(self, _embedding, **_kwargs) -> DuplicateOutcome:
        """Report the face as unique — the partner path stores nothing."""
        return DuplicateOutcome(is_duplicate=False, similarity=0.0)


class _StatelessDuplicateStore:
    """DuplicateStore port that never has anything to search against.

    Keeps the pipeline stateless: no pgvector reads, no FAISS build, no
    enrollment. Every verification is judged on its own liveness and
    face-match, and duplicate detection is effectively off.
    """

    def build_index(self, _tenant_id, *, exclude_client_id) -> _NoMatchIndex:
        """Return an empty index regardless of tenant or client."""
        return _NoMatchIndex()


def authenticate_partner(
    api_key: str | None = Security(_partner_key_header),
) -> str:
    """Authenticate the caller against the single partner secret.

    Raises:
        AuthenticationError: If the partner API is not configured, or the
            presented key is missing or wrong (constant-time compared).
    """
    configured = settings.partner_api_key
    if not configured:
        raise AuthenticationError("Partner API is not enabled.")
    if not api_key or not hmac.compare_digest(api_key, configured):
        raise AuthenticationError("Invalid or missing partner API key.")
    return api_key


def enforce_rate_limit(api_key: str = Depends(authenticate_partner)) -> str:
    """Throttle the authenticated key; 429 when over the per-minute limit."""
    if not _limiter.allow(api_key):
        raise RateLimitedError(
            "Rate limit exceeded. Slow down and retry shortly."
        )
    return api_key


def _read_capped(upload: UploadFile, field: str) -> bytes:
    """Read an upload, rejecting anything over the configured size cap."""
    data = upload.file.read()
    if len(data) > settings.max_upload_bytes:
        limit_mb = settings.max_upload_bytes // (1024 * 1024)
        raise PayloadTooLargeError(
            f"The {field} image exceeds the {limit_mb} MB limit."
        )
    return data


@router.post("/verify", response_model=PartnerVerifyResponse)
def partner_verify(
    document_type: DocumentType = Form(...),
    id_front: UploadFile = File(...),
    selfie: UploadFile = File(...),
    id_back: UploadFile | None = File(None),
    reference: str = Form("", max_length=64),
    _key: str = Depends(enforce_rate_limit),
) -> PartnerVerifyResponse:
    """Run the KYC pipeline over the uploaded images and return the verdict.

    Stateless: no record, no image, and no embedding is persisted, and no
    duplicate search is performed. ``reference`` is an optional correlation
    id echoed back untouched. The response carries the full per-stage
    breakdown for whichever stages ran before the pipeline's early-exit.
    """
    pipeline_input = build_pipeline_input(
        client_id=_STATELESS_CLIENT_REF,
        mfi_account_id=_STATELESS_TENANT_ID,
        document_type=document_type,
        id_front=_read_capped(id_front, "ID front"),
        selfie=_read_capped(selfie, "selfie"),
        id_back=(
            _read_capped(id_back, "ID back") if id_back is not None else None
        ),
    )
    output = run_verification(
        pipeline_input, duplicate_store=_StatelessDuplicateStore()
    )
    result = output.result
    ocr = output.ocr
    return PartnerVerifyResponse(
        reference=reference,
        status=result.status,
        confidence_score=result.confidence,
        reject_reason=result.reject_reason,
        extracted_data=(
            PartnerOcr.model_validate(ocr)
            if ocr is not None and ocr.success
            else None
        ),
        liveness=(
            PartnerLiveness.model_validate(output.liveness)
            if output.liveness is not None
            else None
        ),
        face_match=(
            PartnerFaceMatch.model_validate(output.face_match)
            if output.face_match is not None
            else None
        ),
    )
