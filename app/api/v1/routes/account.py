"""Account and subscription endpoints.

For now this exposes a single read-only summary of the authenticated MFI,
which doubles as the smoke test that API-key auth works end to end. Quota
and billing actions land here in later Phase-2 steps.
"""

from fastapi import APIRouter, Depends

from app.api.v1.deps import Principal, get_principal
from app.schemas.account import AccountSummary

router = APIRouter(prefix="/account", tags=["account"])


@router.get("", response_model=AccountSummary)
def read_account(
    principal: Principal = Depends(get_principal),
) -> AccountSummary:
    """Return the authenticated MFI's account and quota summary.

    Available to any authenticated caller — a machine (API key) or a
    dashboard agent — so the subscription view works from the dashboard.
    """
    mfi = principal.mfi_account
    plan = mfi.plan
    return AccountSummary(
        id=mfi.id,
        name=mfi.name,
        email=mfi.email,
        plan_name=plan.name.value if plan else None,
        verification_quota=plan.verification_quota if plan else None,
        current_period_usage=mfi.current_period_usage,
    )
