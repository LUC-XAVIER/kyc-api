"""Reusable API dependencies: authentication and tenant resolution.

``get_current_mfi`` is the entry gate for every protected endpoint. It
turns an ``X-API-Key`` header into the owning :class:`MfiAccount`, so route
handlers receive an already-authenticated tenant and never touch raw keys.
"""

import uuid
from datetime import UTC, datetime

import jwt
from fastapi import Depends, Security
from fastapi.security import APIKeyHeader, HTTPBearer
from fastapi.security.http import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import decode_access_token, hash_api_key
from app.db.session import get_db
from app.models import Agent, ApiKey, MfiAccount
from app.models.enums import AgentRole, AgentStatus
from app.services import subscription

API_KEY_HEADER_NAME = "X-API-Key"
# auto_error=False: we raise our own AuthenticationError (401 JSON) instead
# of FastAPI's default, so the response shape stays consistent.
_api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)
# Bearer scheme for the human-facing dashboard (agents/managers log in
# with email + password and carry a JWT). Distinct from the X-API-Key
# used by MFIs' own software.
_bearer = HTTPBearer(auto_error=False)


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


def get_current_agent(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
    db: Session = Depends(get_db),
) -> Agent:
    """Authenticate a dashboard session token and return the agent.

    Reads the ``Authorization: Bearer <jwt>`` header, validates the token,
    and loads the referenced :class:`~app.models.mfi.Agent`. A missing,
    malformed, or expired token — or a subject that no longer maps to an
    active account — is rejected.

    Args:
        credentials: The parsed bearer credentials, if present.
        db: Request-scoped database session.

    Returns:
        The authenticated, active :class:`Agent`.

    Raises:
        AuthenticationError: If the token or the referenced account is
            missing, invalid, expired, or disabled.
    """
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Missing bearer token.")

    try:
        claims = decode_access_token(credentials.credentials)
        agent_id = uuid.UUID(claims["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise AuthenticationError("Invalid or expired token.") from None

    agent = db.get(Agent, agent_id)
    if agent is None or agent.status != AgentStatus.ACTIVE:
        raise AuthenticationError("Unknown or disabled account.")
    return agent


def require_manager(
    agent: Agent = Depends(get_current_agent),
) -> Agent:
    """Authorize a manager-only action, returning the acting agent.

    Use in place of :func:`get_current_agent` on endpoints reserved for
    managers (review queue, report generation). Plain agents are refused.

    Args:
        agent: The authenticated agent (from :func:`get_current_agent`).

    Returns:
        The acting :class:`Agent`, guaranteed to hold a manager-level role.

    Raises:
        AuthorizationError: If the agent's role is below ``MANAGER``.
    """
    if agent.role not in (AgentRole.MANAGER, AgentRole.ADMIN):
        raise AuthorizationError("This action requires a manager role.")
    return agent
