"""Dashboard staff authentication.

Agents and managers sign in here with email + password and receive a JWT
session token, which they then present as ``Authorization: Bearer <jwt>``
on dashboard endpoints. This is separate from the ``X-API-Key`` gateway
used by MFIs' own software.
"""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
from fastapi import APIRouter, Depends, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.api.v1.deps import get_current_agent, require_platform_admin
from app.core.config import settings
from app.core.exceptions import (
    AuthenticationError,
    NotFoundError,
    ValidationError,
)
from app.core.security import (
    create_access_token,
    create_mfa_challenge,
    decode_access_token,
    generate_token,
    generate_totp_secret,
    hash_password,
    hash_token,
    totp_provisioning_uri,
    totp_qr_data_uri,
    verify_password,
    verify_totp,
)
from app.core.validation import try_normalize_cm_phone
from app.db.session import get_db
from app.models import PinReset, User
from app.models.enums import AgentRole, AgentStatus, MfiStatus
from app.schemas.auth import (
    AgentProfile,
    ChangePinRequest,
    ForgotPinRequest,
    ForgotPinResponse,
    LoginRequest,
    MfaVerifyRequest,
    ResetPinRequest,
    TokenResponse,
    TwoFactorCodeRequest,
    TwoFactorSetupResponse,
    TwoFactorStatus,
)
from app.services import email as email_service

router = APIRouter(prefix="/auth", tags=["auth"])


def _register_failed_login(db: Session, agent: User, now: datetime) -> None:
    """Count a failed PIN attempt and lock the account at the threshold.

    Committed even though the request ends in an error: the whole point is
    that the count survives, and an exception raised afterwards must not
    roll the increment back.

    Args:
        db: Request-scoped database session.
        agent: The account the failed attempt was made against.
        now: Current UTC time, shared with the caller's lock check.
    """
    agent.failed_login_count += 1
    if agent.failed_login_count >= settings.login_max_attempts:
        agent.locked_until = now + timedelta(
            minutes=settings.login_lockout_minutes
        )
        # Restart the streak so the next failure after the window expires
        # doesn't re-lock the account immediately.
        agent.failed_login_count = 0
    db.commit()


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

    Consecutive PIN failures lock the account for a cooling-off window (see
    ``login_max_attempts``), which is what makes guessing a 6-digit PIN
    infeasible. The lockout message is deliberately distinct from the
    generic failure: it only reaches someone who already knows the
    identifier exists, and a silent lock is indistinguishable from a broken
    login for the legitimate user it inconveniences.

    Args:
        payload: The submitted email and password.
        db: Request-scoped database session.

    Returns:
        The signed token plus the authenticated agent's identity and role.

    Raises:
        AuthenticationError: If the credentials are invalid, the account is
            disabled, or it is inside a lockout window.
    """
    identifier = payload.identifier.strip()
    phone = try_normalize_cm_phone(identifier) or identifier
    agent = (
        db.query(User)
        .filter(or_(User.email == identifier, User.phone == phone))
        .one_or_none()
    )
    if agent is None:
        raise AuthenticationError("Invalid credentials.")

    now = datetime.now(UTC)
    if agent.is_locked(now):
        raise AuthenticationError(
            "Too many failed attempts. Try again later."
        )

    if not agent.hashed_pin or not verify_password(
        payload.pin, agent.hashed_pin
    ):
        _register_failed_login(db, agent, now)
        raise AuthenticationError("Invalid credentials.")
    if agent.status != AgentStatus.ACTIVE:
        raise AuthenticationError("Invalid credentials.")
    # A suspended MFI locks out all its staff. A platform admin has no MFI
    # (mfi_account is None), so they are never blocked here.
    if (
        agent.mfi_account is not None
        and agent.mfi_account.status == MfiStatus.SUSPENDED
    ):
        raise AuthenticationError("This account has been suspended.")

    # A clean login clears the streak; the counter tracks *consecutive*
    # failures, not lifetime ones.
    if agent.failed_login_count or agent.locked_until:
        agent.failed_login_count = 0
        agent.locked_until = None
        db.commit()

    # 2FA gate: the password is correct, but an enrolled account gets no
    # session token yet — only a challenge to exchange for one with a code.
    if agent.totp_enabled and agent.totp_secret:
        return TokenResponse(
            access_token="",
            role=agent.role,
            agent_id=agent.id,
            full_name=agent.full_name,
            mfi_account_id=agent.mfi_account_id,
            mfa_required=True,
            mfa_token=create_mfa_challenge(str(agent.id)),
        )
    return _session_response(agent)


def _session_response(agent: User) -> TokenResponse:
    """Build a full session-token response for an authenticated account."""
    return TokenResponse(
        access_token=create_access_token(
            subject=str(agent.id), role=agent.role.value
        ),
        role=agent.role,
        agent_id=agent.id,
        full_name=agent.full_name,
        mfi_account_id=agent.mfi_account_id,
    )


@router.post("/login/verify", response_model=TokenResponse)
def login_verify(
    payload: MfaVerifyRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Second step of a 2FA login: exchange the challenge + code for a token.

    The ``mfa_token`` proves the password step passed; the ``code`` proves
    possession of the authenticator. Any failure returns the same generic
    error as a bad password.
    """
    try:
        claims = decode_access_token(payload.mfa_token)
        if not claims.get("mfa"):
            raise AuthenticationError("Invalid credentials.")
        agent_id = uuid.UUID(claims["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError):
        raise AuthenticationError("Invalid credentials.") from None

    agent = db.get(User, agent_id)
    if (
        agent is None
        or agent.status != AgentStatus.ACTIVE
        or not agent.totp_enabled
        or not agent.totp_secret
        or not verify_totp(agent.totp_secret, payload.code)
    ):
        raise AuthenticationError("Invalid credentials.")
    return _session_response(agent)


@router.get("/me", response_model=AgentProfile)
def read_me(agent: User = Depends(get_current_agent)) -> AgentProfile:
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
        branch=agent.branch_name,
        mfi_account_id=agent.mfi_account_id,
        mfi_name=agent.mfi_account.name if agent.mfi_account else None,
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
        db.query(User)
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
        db.query(User)
        .filter_by(email=reset.email, role=AgentRole.MANAGER)
        .one_or_none()
    )
    if agent is None:
        raise NotFoundError("Account not found.")

    agent.hashed_pin = hash_password(payload.pin)
    reset.used_at = datetime.now(UTC)
    db.flush()
    return {"status": "reset"}


@router.post("/change-pin", status_code=status.HTTP_200_OK)
def change_pin(
    payload: ChangePinRequest,
    agent: User = Depends(get_current_agent),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Let a signed-in user change their own PIN (current PIN required)."""
    if not agent.hashed_pin or not verify_password(
        payload.current_pin, agent.hashed_pin
    ):
        # A 400 (not 401): the session is valid, only the entered PIN is
        # wrong. A 401 would trip the client's auto-logout on expired sessions.
        raise ValidationError("Current PIN is incorrect.")
    agent.hashed_pin = hash_password(payload.new_pin)
    db.flush()
    return {"status": "changed"}


# --- Two-factor authentication (platform admin) -----------------------


@router.get("/2fa", response_model=TwoFactorStatus)
def two_factor_status(
    admin: User = Depends(require_platform_admin),
) -> TwoFactorStatus:
    """Whether 2FA is currently enabled on the admin account."""
    return TwoFactorStatus(enabled=admin.totp_enabled)


@router.post("/2fa/setup", response_model=TwoFactorSetupResponse)
def two_factor_setup(
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> TwoFactorSetupResponse:
    """Begin enrolment: mint a secret and return it once for the app to scan.

    Stored but not yet active — the admin must confirm a code via
    ``/2fa/enable`` before the login challenge turns on. Re-running before
    enabling simply rotates the pending secret.
    """
    if admin.totp_enabled:
        raise ValidationError("Two-factor is already enabled.")
    secret = generate_totp_secret()
    admin.totp_secret = secret
    db.commit()
    uri = totp_provisioning_uri(secret, admin.email or "admin")
    return TwoFactorSetupResponse(
        secret=secret, otpauth_uri=uri, qr=totp_qr_data_uri(uri)
    )


@router.post("/2fa/enable", status_code=status.HTTP_200_OK)
def two_factor_enable(
    payload: TwoFactorCodeRequest,
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Confirm enrolment: verify a code against the pending secret."""
    if not admin.totp_secret:
        raise ValidationError("Start two-factor setup first.")
    if not verify_totp(admin.totp_secret, payload.code):
        raise ValidationError("That code is invalid or expired.")
    admin.totp_enabled = True
    db.commit()
    return {"status": "enabled"}


@router.post("/2fa/disable", status_code=status.HTTP_200_OK)
def two_factor_disable(
    payload: TwoFactorCodeRequest,
    admin: User = Depends(require_platform_admin),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Turn 2FA off — a current code is required to do it."""
    if not admin.totp_enabled or not admin.totp_secret:
        raise ValidationError("Two-factor is not enabled.")
    if not verify_totp(admin.totp_secret, payload.code):
        raise ValidationError("That code is invalid or expired.")
    admin.totp_enabled = False
    admin.totp_secret = None
    db.commit()
    return {"status": "disabled"}
