"""Account and subscription endpoints for the authenticated MFI."""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.v1.deps import (
    Principal,
    get_principal,
    require_manager_principal,
)
from app.core.exceptions import ValidationError
from app.db.session import get_db
from app.models import MfiAccount
from app.schemas.account import AccountSummary, AccountUpdate

router = APIRouter(prefix="/account", tags=["account"])


def _summary(mfi: MfiAccount) -> AccountSummary:
    plan = mfi.plan
    return AccountSummary(
        id=mfi.id,
        name=mfi.name,
        email=mfi.email,
        plan_name=plan.name.value if plan else None,
        verification_quota=plan.verification_quota if plan else None,
        current_period_usage=mfi.current_period_usage,
    )


@router.get("", response_model=AccountSummary)
def read_account(
    principal: Principal = Depends(get_principal),
) -> AccountSummary:
    """Return the MFI's account + quota (any authenticated caller)."""
    return _summary(principal.mfi_account)


@router.patch("", response_model=AccountSummary)
def update_account(
    payload: AccountUpdate,
    principal: Principal = Depends(require_manager_principal),
    db: Session = Depends(get_db),
) -> AccountSummary:
    """Update the MFI profile (name / contact email) — manager only."""
    mfi = principal.mfi_account
    if payload.name is not None:
        mfi.name = payload.name.strip()
    if payload.email is not None:
        email = payload.email.strip()
        clash = (
            db.query(MfiAccount)
            .filter(MfiAccount.email == email, MfiAccount.id != mfi.id)
            .first()
        )
        if clash is not None:
            raise ValidationError("That email is already in use.")
        mfi.email = email
    db.flush()
    return _summary(mfi)
