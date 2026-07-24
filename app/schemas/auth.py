"""Request/response schemas for dashboard staff authentication."""

import uuid

from pydantic import BaseModel, Field

from app.models.enums import AgentRole


class LoginRequest(BaseModel):
    """Credentials posted at the dashboard login.

    ``identifier`` is the manager's email or the agent's phone number;
    ``pin`` is the 6-8 character PIN shared by both roles.
    """

    identifier: str
    pin: str


class TokenResponse(BaseModel):
    """A minted session token plus the identity it authenticates.

    The client stores ``access_token`` and sends it as a bearer token; the
    remaining fields let the dashboard render the right role surface
    without decoding the JWT itself.
    """

    access_token: str
    token_type: str = "bearer"
    role: AgentRole
    agent_id: uuid.UUID
    full_name: str
    # None for a platform admin, who belongs to no single MFI.
    mfi_account_id: uuid.UUID | None = None
    # When the account has 2FA enabled, the password step returns no session
    # token: instead ``mfa_required`` is true and ``mfa_token`` is a
    # short-lived challenge to exchange (with a TOTP code) for the real token.
    mfa_required: bool = False
    mfa_token: str | None = None


class MfaVerifyRequest(BaseModel):
    """Second login step: a challenge token plus the authenticator code."""

    mfa_token: str
    code: str


class TwoFactorSetupResponse(BaseModel):
    """Enrolment payload — shown once so the admin can scan/store it."""

    secret: str
    otpauth_uri: str
    qr: str  # inline SVG data URI of the otpauth URI


class TwoFactorCodeRequest(BaseModel):
    """A 6-digit TOTP code, to enable or disable 2FA."""

    code: str


class TwoFactorStatus(BaseModel):
    """Whether 2FA is currently active on the account."""

    enabled: bool


class ForgotPinRequest(BaseModel):
    """A manager requesting a PIN-reset link by email."""

    email: str


class ForgotPinResponse(BaseModel):
    """Ack (always the same). ``reset_link`` is only set in dev."""

    status: str = "sent"
    reset_link: str | None = None


class ResetPinRequest(BaseModel):
    """A manager setting a new PIN with a reset token."""

    token: str
    pin: str = Field(min_length=6, max_length=8)


class ChangePinRequest(BaseModel):
    """A signed-in user changing their own PIN."""

    current_pin: str
    new_pin: str = Field(min_length=6, max_length=8)


class AgentProfile(BaseModel):
    """The signed-in agent's own profile (``GET /auth/me``)."""

    agent_id: uuid.UUID
    full_name: str
    email: str | None
    phone: str | None
    role: AgentRole
    branch: str | None
    # None for a platform admin, who belongs to no single MFI.
    mfi_account_id: uuid.UUID | None = None
    mfi_name: str | None = None
