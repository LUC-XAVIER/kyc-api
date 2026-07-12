"""Request/response schemas for dashboard staff authentication."""

import uuid

from pydantic import BaseModel

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
