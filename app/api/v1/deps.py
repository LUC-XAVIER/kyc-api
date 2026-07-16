"""Reusable API dependencies: authentication, tenancy, and roles.

Two credentials authenticate a caller:

* an ``X-API-Key`` header — the MFI's own software (machine integration);
* an ``Authorization: Bearer <jwt>`` token — a human agent/manager signed
  into the dashboard.

:func:`get_principal` accepts either and yields a :class:`Principal` that
carries the tenant, the acting agent (if any), and whether the caller has
manager-level authority. An API key is trusted as full tenant access; a
bearer token carries the agent's specific role.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

import jwt
from fastapi import Depends, Security
from fastapi.security import APIKeyHeader, HTTPBearer
from fastapi.security.http import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import decode_access_token, hash_api_key
from app.db.session import get_db
from app.models import ApiKey, MfiAccount, User
from app.models.enums import ActorType, AgentRole, AgentStatus
from app.services import subscription

API_KEY_HEADER_NAME = "X-API-Key"
# auto_error=False: we raise our own AuthenticationError (401 JSON) instead
# of FastAPI's default, so the response shape stays consistent.
_api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)
# Bearer scheme for the human-facing dashboard (agents/managers log in
# with email + password and carry a JWT). Distinct from the X-API-Key
# used by MFIs' own software.
_bearer = HTTPBearer(auto_error=False)

_MANAGER_ROLES = (AgentRole.MANAGER, AgentRole.ADMIN)
# Maps an agent's role to the audit-log actor type; a machine (API-key)
# caller has no agent and is recorded as SYSTEM.
_ROLE_TO_ACTOR = {
    AgentRole.AGENT: ActorType.AGENT,
    AgentRole.MANAGER: ActorType.MANAGER,
    AgentRole.ADMIN: ActorType.ADMIN,
}


def _mfi_from_key(api_key: str, db: Session) -> MfiAccount:
    """Resolve an active API key to its MFI, touching ``last_used_at``."""
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


def _agent_from_token(token: str, db: Session) -> User:
    """Validate a session JWT and return its active agent."""
    try:
        claims = decode_access_token(token)
        agent_id = uuid.UUID(claims["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise AuthenticationError("Invalid or expired token.") from None

    agent = db.get(User, agent_id)
    if agent is None or agent.status != AgentStatus.ACTIVE:
        raise AuthenticationError("Unknown or disabled account.")
    return agent


def get_current_mfi(
    api_key: str | None = Security(_api_key_header),
    db: Session = Depends(get_db),
) -> MfiAccount:
    """Authenticate by API key and return the owning MFI account.

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
    return _mfi_from_key(api_key, db)


def get_metered_mfi(
    mfi: MfiAccount = Depends(get_current_mfi),
    db: Session = Depends(get_db),
) -> MfiAccount:
    """Authenticate by API key, roll the billing period, enforce quota.

    Raises:
        QuotaExceededError: If the account is over its plan limit.
    """
    subscription.roll_period_if_needed(db, mfi)
    subscription.enforce_quota(mfi)
    return mfi


def get_current_agent(
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
    db: Session = Depends(get_db),
) -> User:
    """Authenticate a dashboard session token and return the agent.

    Args:
        credentials: The parsed bearer credentials, if present.
        db: Request-scoped database session.

    Returns:
        The authenticated, active :class:`User`.

    Raises:
        AuthenticationError: If the token or the referenced account is
            missing, invalid, expired, or disabled.
    """
    if credentials is None or not credentials.credentials:
        raise AuthenticationError("Missing bearer token.")
    return _agent_from_token(credentials.credentials, db)


def require_manager(
    agent: User = Depends(get_current_agent),
) -> User:
    """Authorize a manager-only, bearer-authenticated action.

    Raises:
        AuthorizationError: If the agent's role is below ``MANAGER``.
    """
    if agent.role not in _MANAGER_ROLES:
        raise AuthorizationError("This action requires a manager role.")
    return agent


@dataclass
class Principal:
    """The authenticated caller behind a request.

    Attributes:
        mfi_account: The owning tenant, used for row-level scoping.
        agent: The human agent, when the caller signed in via the
            dashboard; ``None`` for a machine (API-key) caller.
        is_manager: Whether the caller may perform manager-only actions
            (any API-key caller, or an agent with a manager-level role).
    """

    mfi_account: MfiAccount
    agent: User | None
    is_manager: bool

    @property
    def actor_type(self) -> ActorType:
        """The audit actor type for this caller."""
        if self.agent is None:
            return ActorType.SYSTEM
        return _ROLE_TO_ACTOR[self.agent.role]

    @property
    def actor_id(self) -> str | None:
        """The acting agent's id as a string, or ``None`` for a machine."""
        return str(self.agent.id) if self.agent else None


def get_principal(
    api_key: str | None = Security(_api_key_header),
    credentials: HTTPAuthorizationCredentials | None = Security(_bearer),
    db: Session = Depends(get_db),
) -> Principal:
    """Authenticate via bearer token or API key into a :class:`Principal`.

    A dashboard bearer token takes precedence when both are present. The
    API key is trusted as full tenant access (``is_manager=True``); a
    bearer token carries the agent's own role.

    Raises:
        AuthenticationError: If neither credential is present or valid.
    """
    if credentials is not None and credentials.credentials:
        agent = _agent_from_token(credentials.credentials, db)
        return Principal(
            mfi_account=agent.mfi_account,
            agent=agent,
            is_manager=agent.role in _MANAGER_ROLES,
        )
    if api_key:
        return Principal(
            mfi_account=_mfi_from_key(api_key, db),
            agent=None,
            is_manager=True,
        )
    raise AuthenticationError("Missing credentials.")


def get_metered_principal(
    principal: Principal = Depends(get_principal),
    db: Session = Depends(get_db),
) -> Principal:
    """Authenticate any caller, roll the billing period, enforce quota.

    Raises:
        QuotaExceededError: If the account is over its plan limit.
    """
    subscription.roll_period_if_needed(db, principal.mfi_account)
    subscription.enforce_quota(principal.mfi_account)
    return principal


def require_manager_principal(
    principal: Principal = Depends(get_principal),
) -> Principal:
    """Authorize a manager-level action by any authenticated caller.

    Accepts an API-key caller (machine, full access) or a manager/admin
    agent; a plain agent is refused.

    Raises:
        AuthorizationError: If the caller lacks manager authority.
    """
    if not principal.is_manager:
        raise AuthorizationError("This action requires a manager role.")
    return principal
