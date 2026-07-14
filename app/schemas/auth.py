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
    mfi_account_id: uuid.UUID


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
    mfi_account_id: uuid.UUID
    mfi_name: str
