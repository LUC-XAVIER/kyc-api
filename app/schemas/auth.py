"""Request/response schemas for dashboard staff authentication."""

import uuid

from pydantic import BaseModel

from app.models.enums import AgentRole


class LoginRequest(BaseModel):
    """Credentials posted by a staff member at the dashboard login."""

    email: str
    password: str


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
