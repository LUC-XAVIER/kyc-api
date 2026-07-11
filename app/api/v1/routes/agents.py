"""MFI agent (dashboard staff) management — manager only.

A manager lists the MFI's agents, provisions new ones (with login
credentials and a role), and updates an agent's role, branch, or status.
Agent creation respects the subscription plan's agent limit.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.v1.deps import Principal, require_manager_principal
from app.core.exceptions import NotFoundError, ValidationError
from app.core.security import hash_password
from app.db.session import get_db
from app.models import Agent
from app.models.enums import AgentRole
from app.schemas.agent import AgentCreate, AgentSummary, AgentUpdate

router = APIRouter(prefix="/agents", tags=["agents"])


def _guard_assignable_role(role: AgentRole) -> None:
    """Reject roles a manager may not hand out (the platform ADMIN role)."""
    if role is AgentRole.ADMIN:
        raise ValidationError("The ADMIN role cannot be assigned.")


@router.get("", response_model=list[AgentSummary])
def list_agents(
    principal: Principal = Depends(require_manager_principal),
    db: Session = Depends(get_db),
) -> list[Agent]:
    """List the MFI's agents, ordered by name."""
    return (
        db.query(Agent)
        .filter_by(mfi_account_id=principal.mfi_account.id)
        .order_by(Agent.full_name)
        .all()
    )


@router.post(
    "", response_model=AgentSummary, status_code=status.HTTP_201_CREATED
)
def create_agent(
    payload: AgentCreate,
    principal: Principal = Depends(require_manager_principal),
    db: Session = Depends(get_db),
) -> Agent:
    """Provision a new agent under the caller's MFI.

    Enforces the plan's agent limit and a globally-unique email.
    """
    _guard_assignable_role(payload.role)
    mfi = principal.mfi_account

    plan = mfi.plan
    if plan is not None and plan.max_agents is not None:
        existing = (
            db.query(Agent).filter_by(mfi_account_id=mfi.id).count()
        )
        if existing >= plan.max_agents:
            raise ValidationError(
                "Your plan's agent limit has been reached."
            )

    if db.query(Agent).filter_by(email=payload.email).first() is not None:
        raise ValidationError("That email is already in use.")

    agent = Agent(
        mfi_account_id=mfi.id,
        full_name=payload.full_name,
        email=payload.email,
        hashed_password=hash_password(payload.password),
        branch=payload.branch,
        role=payload.role,
    )
    db.add(agent)
    db.flush()
    return agent


@router.patch("/{agent_id}", response_model=AgentSummary)
def update_agent(
    agent_id: uuid.UUID,
    payload: AgentUpdate,
    principal: Principal = Depends(require_manager_principal),
    db: Session = Depends(get_db),
) -> Agent:
    """Update an agent's name, branch, role, or status."""
    agent = (
        db.query(Agent)
        .filter_by(id=agent_id, mfi_account_id=principal.mfi_account.id)
        .one_or_none()
    )
    if agent is None:
        raise NotFoundError("Agent not found.")

    if payload.role is not None:
        _guard_assignable_role(payload.role)
        agent.role = payload.role
    if payload.full_name is not None:
        agent.full_name = payload.full_name
    if payload.branch is not None:
        agent.branch = payload.branch
    if payload.status is not None:
        agent.status = payload.status
    db.flush()
    return agent
