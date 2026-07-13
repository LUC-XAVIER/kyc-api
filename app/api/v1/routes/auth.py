"""Dashboard staff authentication.

Agents and managers sign in here with email + password and receive a JWT
session token, which they then present as ``Authorization: Bearer <jwt>``
on dashboard endpoints. This is separate from the ``X-API-Key`` gateway
used by MFIs' own software.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_agent
from app.core.config import settings
from app.core.exceptions import (
    AuthenticationError,
    NotFoundError,
    ValidationError,
)
from app.core.security import (
    create_access_token,
    generate_token,
    hash_password,
    hash_token,
    verify_password,
)
from app.db.session import get_db
from app.models import Agent, PinReset
from app.models.enums import AgentRole, AgentStatus
from app.schemas.auth import (
    AgentProfile,
    ForgotPinRequest,
    ForgotPinResponse,
    LoginRequest,
    ResetPinRequest,
    TokenResponse,
)
from app.services import email as email_service

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


@router.post(
    "/forgot-pin",
    response_model=ForgotPinResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def forgot_pin(
    payload: ForgotPinRequest, db: Session = Depends(get_db)
) -> ForgotPinResponse:
    """Email an active manager a PIN-reset link.

    Always returns the same response whether or not the email matches a
    manager, so it can't be used to probe for accounts. (Agents have no
    email — their PIN is reset by a manager.)
    """
    email = payload.email.strip().lower()
    agent = (
        db.query(Agent)
        .filter_by(
            email=email,
            role=AgentRole.MANAGER,
            status=AgentStatus.ACTIVE,
        )
        .one_or_none()
    )
    link = None
    if agent is not None:
        token = generate_token()
        db.add(
            PinReset(
                email=email,
                token_hash=hash_token(token),
                expires_at=datetime.now(UTC)
                + timedelta(hours=settings.reset_token_ttl_hours),
            )
        )
        db.flush()
        email_service.send_pin_reset(email, token)
        if not settings.email_enabled:
            link = email_service.reset_link(token)
    return ForgotPinResponse(reset_link=link)


@router.post("/reset-pin", status_code=status.HTTP_200_OK)
def reset_pin(
    payload: ResetPinRequest, db: Session = Depends(get_db)
) -> dict[str, str]:
    """Consume a valid reset token and set the manager's new PIN."""
    reset = (
        db.query(PinReset)
        .filter_by(token_hash=hash_token(payload.token))
        .one_or_none()
    )
    if reset is None:
        raise NotFoundError("Invalid reset link.")
    if reset.used_at is not None:
        raise ValidationError("This reset link has already been used.")
    if reset.expires_at < datetime.now(UTC):
        raise ValidationError("This reset link has expired.")

    agent = (
        db.query(Agent)
        .filter_by(email=reset.email, role=AgentRole.MANAGER)
        .one_or_none()
    )
    if agent is None:
        raise NotFoundError("Account not found.")

    agent.hashed_password = hash_password(payload.pin)
    reset.used_at = datetime.now(UTC)
    db.flush()
    return {"status": "reset"}
