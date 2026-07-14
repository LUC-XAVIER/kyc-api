"""MFI agent (field staff) management — manager only.

A manager lists the MFI's agents, provisions new ones (name, phone, and an
initial PIN — agents have no email), updates an agent's name/branch/status,
and re-initialises an agent's PIN when they forget it.
"""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.v1.deps import Principal, require_manager_principal
from app.core.exceptions import NotFoundError, ValidationError
from app.core.security import hash_password
from app.db.session import get_db
from app.models import Branch, User
from app.models.enums import AgentRole
from app.schemas.agent import (
    AgentCreate,
    AgentPinReset,
    AgentSummary,
    AgentUpdate,
)

router = APIRouter(prefix="/agents", tags=["agents"])


def _owned_agent(
    db: Session, agent_id: uuid.UUID, principal: Principal
) -> User:
    """Return the agent if it belongs to the caller's MFI, else 404."""
    agent = (
        db.query(User)
        .filter_by(id=agent_id, mfi_account_id=principal.mfi_account.id)
        .one_or_none()
    )
    if agent is None:
        raise NotFoundError("Agent not found.")
    return agent


def _require_branch(
    db: Session, branch_id: uuid.UUID, mfi_account_id: uuid.UUID
) -> None:
    """Ensure ``branch_id`` is a branch of the caller's MFI."""
    branch = (
        db.query(Branch)
        .filter_by(id=branch_id, mfi_account_id=mfi_account_id)
        .one_or_none()
    )
    if branch is None:
        raise ValidationError("Unknown branch for this MFI.")


@router.get("", response_model=list[AgentSummary])
def list_agents(
    principal: Principal = Depends(require_manager_principal),
    db: Session = Depends(get_db),
) -> list[User]:
    """List the MFI's agents, ordered by name."""
    return (
        db.query(User)
        .filter_by(mfi_account_id=principal.mfi_account.id)
        .order_by(User.full_name)
        .all()
    )


@router.post(
    "", response_model=AgentSummary, status_code=status.HTTP_201_CREATED
)
def create_agent(
    payload: AgentCreate,
    principal: Principal = Depends(require_manager_principal),
    db: Session = Depends(get_db),
) -> User:
    """Provision a new field agent (phone + initial PIN, no email).

    Enforces the plan's agent limit and a globally-unique phone number.
    """
    mfi = principal.mfi_account

    plan = mfi.plan
    if plan is not None and plan.max_agents is not None:
        existing = (
            db.query(User).filter_by(mfi_account_id=mfi.id).count()
        )
        if existing >= plan.max_agents:
            raise ValidationError(
                "Your plan's agent limit has been reached."
            )

    if db.query(User).filter_by(phone=payload.phone).first() is not None:
        raise ValidationError("That phone number is already in use.")

    _require_branch(db, payload.branch_id, mfi.id)

    agent = User(
        mfi_account_id=mfi.id,
        full_name=payload.full_name,
        phone=payload.phone,
        hashed_pin=hash_password(payload.pin),
        branch_id=payload.branch_id,
        role=AgentRole.AGENT,
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
) -> User:
    """Update an agent's name, branch, or status."""
    agent = _owned_agent(db, agent_id, principal)
    if payload.full_name is not None:
        agent.full_name = payload.full_name
    if payload.branch_id is not None:
        _require_branch(db, payload.branch_id, principal.mfi_account.id)
        agent.branch_id = payload.branch_id
    if payload.status is not None:
        agent.status = payload.status
    db.flush()
    return agent


@router.post("/{agent_id}/reset-pin", response_model=AgentSummary)
def reset_agent_pin(
    agent_id: uuid.UUID,
    payload: AgentPinReset,
    principal: Principal = Depends(require_manager_principal),
    db: Session = Depends(get_db),
) -> User:
    """Re-initialise an agent's PIN (for an agent who forgot theirs)."""
    agent = _owned_agent(db, agent_id, principal)
    agent.hashed_pin = hash_password(payload.pin)
    db.flush()
    return agent
