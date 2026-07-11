"""MFI API-key management — manager only.

Managers mint API keys for their own software (the machine integration
that calls ``/kyc/verify``), list them, and revoke them. The plaintext
secret is shown exactly once, at creation; only its prefix and hash are
stored (see :mod:`app.core.security`).
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.v1.deps import Principal, require_manager_principal
from app.core.exceptions import NotFoundError
from app.core.security import generate_api_key
from app.db.session import get_db
from app.models import ApiKey
from app.schemas.api_key import ApiKeyCreated, ApiKeySummary

router = APIRouter(prefix="/api-keys", tags=["api-keys"])


@router.get("", response_model=list[ApiKeySummary])
def list_api_keys(
    principal: Principal = Depends(require_manager_principal),
    db: Session = Depends(get_db),
) -> list[ApiKey]:
    """List the MFI's API keys, newest first (secrets never included)."""
    return (
        db.query(ApiKey)
        .filter_by(mfi_account_id=principal.mfi_account.id)
        .order_by(ApiKey.created_at.desc())
        .all()
    )


@router.post(
    "", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED
)
def create_api_key(
    principal: Principal = Depends(require_manager_principal),
    db: Session = Depends(get_db),
) -> ApiKeyCreated:
    """Mint a new API key and return its secret exactly once."""
    generated = generate_api_key()
    key = ApiKey(
        mfi_account_id=principal.mfi_account.id,
        hashed_key=generated.hashed_key,
        prefix=generated.prefix,
    )
    db.add(key)
    db.flush()
    db.refresh(key)
    return ApiKeyCreated(
        id=key.id,
        prefix=key.prefix,
        full_key=generated.full_key,
        created_at=key.created_at,
    )


@router.delete("/{key_id}", response_model=ApiKeySummary)
def revoke_api_key(
    key_id: uuid.UUID,
    principal: Principal = Depends(require_manager_principal),
    db: Session = Depends(get_db),
) -> ApiKey:
    """Revoke (deactivate) one of the MFI's API keys."""
    key = (
        db.query(ApiKey)
        .filter_by(id=key_id, mfi_account_id=principal.mfi_account.id)
        .one_or_none()
    )
    if key is None:
        raise NotFoundError("API key not found.")
    key.is_active = False
    db.flush()
    return key
