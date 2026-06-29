"""Reusable API dependencies: authentication and tenant resolution.

``get_current_mfi`` is the entry gate for every protected endpoint. It
turns an ``X-API-Key`` header into the owning :class:`MfiAccount`, so route
handlers receive an already-authenticated tenant and never touch raw keys.
"""

from datetime import UTC, datetime

from fastapi import Depends, Security
from fastapi.security import APIKeyHeader
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError
from app.core.security import hash_api_key
from app.db.session import get_db
from app.models import ApiKey, MfiAccount
from app.services import subscription

API_KEY_HEADER_NAME = "X-API-Key"
# auto_error=False: we raise our own AuthenticationError (401 JSON) instead
# of FastAPI's default, so the response shape stays consistent.
_api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)


def get_current_mfi(
    api_key: str | None = Security(_api_key_header),
    db: Session = Depends(get_db),
) -> MfiAccount:
    """Authenticate by API key and return the owning MFI account.

    The key is looked up by its HMAC digest (deterministic and uniquely
    indexed), so the lookup itself is the verification. Missing, unknown,
    or deactivated keys are rejected. The matched key's ``last_used_at`` is
    refreshed as a side effect.

    Args:
        api_key: Value of the ``X-API-Key`` request header, if present.
        db: Request-scoped database session.

    Returns:
        The authenticated :class:`~app.models.mfi.MfiAccount`.

    Raises:
        AuthenticationError: If the key is absent, unknown, or inactive.
    """
    if not api_key:
        raise AuthenticationError("Missing API key.")

    record = (
        db.query(ApiKey)
        .filter_by(hashed_key=hash_api_key(api_key), is_active=True)
        .one_or_none()
    )
    if record is None:
        raise AuthenticationError("Invalid or inactive API key.")

    record.last_used_at = datetime.now(UTC)
    db.commit()
    return record.mfi_account


def get_metered_mfi(
    mfi: MfiAccount = Depends(get_current_mfi),
    db: Session = Depends(get_db),
) -> MfiAccount:
    """Authenticate, roll the billing period, and enforce the quota.

    Use this in place of :func:`get_current_mfi` on metered endpoints: it
    blocks (402) when the account has exhausted its monthly quota.

    Args:
        mfi: The authenticated account (from :func:`get_current_mfi`).
        db: Request-scoped database session.

    Returns:
        The authenticated, quota-cleared :class:`MfiAccount`.

    Raises:
        QuotaExceededError: If the account is over its plan limit.
    """
    subscription.roll_period_if_needed(db, mfi)
    subscription.enforce_quota(mfi)
    return mfi
