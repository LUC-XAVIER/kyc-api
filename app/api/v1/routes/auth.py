"""Dashboard staff authentication.

Agents and managers sign in here with email + password and receive a JWT
session token, which they then present as ``Authorization: Bearer <jwt>``
on dashboard endpoints. This is separate from the ``X-API-Key`` gateway
used by MFIs' own software.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.exceptions import AuthenticationError
from app.core.security import create_access_token, verify_password
from app.db.session import get_db
from app.models import Agent
from app.models.enums import AgentStatus
from app.schemas.auth import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Authenticate a staff member and issue a session token.

    Verifies the email/password pair against the agent record and, on
    success, mints a JWT carrying the agent's id and role. Unknown emails,
    wrong passwords, and disabled accounts all return the same generic
    error so the endpoint cannot be used to enumerate accounts.

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
        db.query(Agent).filter_by(email=payload.email).one_or_none()
    )
    if (
        agent is None
        or not agent.hashed_password
        or not verify_password(payload.password, agent.hashed_password)
    ):
        raise AuthenticationError("Invalid email or password.")
    if agent.status != AgentStatus.ACTIVE:
        raise AuthenticationError("Invalid email or password.")

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
