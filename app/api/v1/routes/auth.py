"""Dashboard staff authentication.

Agents and managers sign in here with email + password and receive a JWT
session token, which they then present as ``Authorization: Bearer <jwt>``
on dashboard endpoints. This is separate from the ``X-API-Key`` gateway
used by MFIs' own software.
"""

from fastapi import APIRouter, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_agent
from app.core.exceptions import AuthenticationError
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models import Agent
from app.models.enums import AgentStatus
from app.schemas.auth import AgentProfile, LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Authenticate a staff member and issue a session token.

    Looks the account up by email or phone, verifies the PIN, and mints a
    JWT carrying the agent's id and role. Unknown identifiers, wrong PINs,
    and disabled accounts all return the same generic error so the endpoint
    cannot be used to enumerate accounts.

    Args:
        payload: The submitted email and password.
        db: Request-scoped database session.

    Returns:
        The signed token plus the authenticated agent's identity and role.

    Raises:
        AuthenticationError: If the credentials are invalid or the account
            is disabled.
    """
    agent = (
        db.query(Agent)
        .filter(
            or_(
                Agent.email == payload.identifier,
                Agent.phone == payload.identifier,
            )
        )
        .one_or_none()
    )
    if (
        agent is None
        or not agent.hashed_password
        or not verify_password(payload.pin, agent.hashed_password)
    ):
        raise AuthenticationError("Invalid credentials.")
    if agent.status != AgentStatus.ACTIVE:
        raise AuthenticationError("Invalid credentials.")

    token = create_access_token(
        subject=str(agent.id), role=agent.role.value
    )
    return TokenResponse(
        access_token=token,
        role=agent.role,
        agent_id=agent.id,
        full_name=agent.full_name,
        mfi_account_id=agent.mfi_account_id,
    )


@router.get("/me", response_model=AgentProfile)
def read_me(agent: Agent = Depends(get_current_agent)) -> AgentProfile:
    """Return the signed-in agent's own profile.

    Lets the dashboard confirm a stored token is still valid and refresh
    the agent's identity/role without re-decoding the JWT itself.
    """
    return AgentProfile(
        agent_id=agent.id,
        full_name=agent.full_name,
        email=agent.email,
        phone=agent.phone,
        role=agent.role,
        branch=agent.branch,
        mfi_account_id=agent.mfi_account_id,
        mfi_name=agent.mfi_account.name,
    )
