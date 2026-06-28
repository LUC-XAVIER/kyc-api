"""Account and subscription endpoints.

For now this exposes a single read-only summary of the authenticated MFI,
which doubles as the smoke test that API-key auth works end to end. Quota
and billing actions land here in later Phase-2 steps.
"""

from fastapi import APIRouter, Depends

from app.api.v1.deps import get_current_mfi
from app.models import MfiAccount
from app.schemas.account import AccountSummary

router = APIRouter(prefix="/account", tags=["account"])


@router.get("", response_model=AccountSummary)
def read_account(
    mfi: MfiAccount = Depends(get_current_mfi),
) -> AccountSummary:
    """Return the authenticated MFI's account and quota summary."""
    plan = mfi.plan
    return AccountSummary(
        id=mfi.id,
        name=mfi.name,
        email=mfi.email,
        plan_name=plan.name.value if plan else None,
        verification_quota=plan.verification_quota if plan else None,
        current_period_usage=mfi.current_period_usage,
    )
