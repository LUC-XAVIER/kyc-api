"""Self-service manager onboarding (public — no auth).

Landing page: choose a plan and enter an email -> we create a pending invite
and email a signup link. The link opens the signup form (email pre-filled),
which posts back here to create the MFI account and its first manager.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.security import generate_token, hash_password, hash_token
from app.db.session import get_db
from app.models import MfiAccount, SignupInvite, SubscriptionPlan, User
from app.models.enums import AgentRole, AgentStatus, MfiStatus, PlanName
from app.schemas.onboarding import (
    CompleteResponse,
    InviteInfo,
    OnboardingComplete,
    OnboardingStart,
    StartResponse,
)
from app.services import email as email_service

router = APIRouter(prefix="/onboarding", tags=["onboarding"])


def _resolve_plan(db: Session, plan_value: str) -> SubscriptionPlan:
    try:
        name = PlanName(plan_value)
    except ValueError:
        raise ValidationError("Unknown plan.") from None
    plan = db.query(SubscriptionPlan).filter_by(name=name).one_or_none()
    if plan is None:
        raise ValidationError("That plan is not available.")
    return plan


def _valid_invite(db: Session, token: str) -> SignupInvite:
    invite = (
        db.query(SignupInvite)
        .filter_by(token_hash=hash_token(token))
        .one_or_none()
    )
    if invite is None:
        raise NotFoundError("Invalid signup link.")
    if invite.completed_at is not None:
        raise ValidationError("This signup link has already been used.")
    if invite.expires_at < datetime.now(UTC):
        raise ValidationError("This signup link has expired.")
    return invite


@router.post(
    "/start",
    response_model=StartResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_onboarding(
    payload: OnboardingStart, db: Session = Depends(get_db)
) -> StartResponse:
    """Validate the plan, create a pending invite, and email the link."""
    _resolve_plan(db, payload.plan)
    email = payload.email.strip().lower()
    token = generate_token()
    invite = SignupInvite(
        email=email,
        plan=payload.plan,
        token_hash=hash_token(token),
        expires_at=datetime.now(UTC)
        + timedelta(hours=settings.signup_token_ttl_hours),
    )
    db.add(invite)
    db.flush()
    email_service.send_signup_invite(email, token)
    # In dev (email disabled) hand the link back so the flow is testable.
    link = None if settings.email_enabled else email_service.signup_link(
        token
    )
    return StartResponse(signup_link=link)


@router.get("/invite/{token}", response_model=InviteInfo)
def read_invite(
    token: str, db: Session = Depends(get_db)
) -> InviteInfo:
    """Return the email + plan behind a valid signup token."""
    invite = _valid_invite(db, token)
    return InviteInfo(email=invite.email, plan=invite.plan)


@router.post(
    "/complete",
    response_model=CompleteResponse,
    status_code=status.HTTP_201_CREATED,
)
def complete_onboarding(
    payload: OnboardingComplete, db: Session = Depends(get_db)
) -> CompleteResponse:
    """Create the MFI account + first manager from a valid signup token."""
    invite = _valid_invite(db, payload.token)
    plan = _resolve_plan(db, invite.plan)

    if db.query(User).filter_by(email=invite.email).first() is not None:
        raise ValidationError("An account already exists for this email.")
    if (
        db.query(MfiAccount).filter_by(email=invite.email).first()
        is not None
    ):
        raise ValidationError("An account already exists for this email.")
    if (
        payload.phone
        and db.query(User).filter_by(phone=payload.phone).first()
        is not None
    ):
        raise ValidationError("That phone number is already in use.")

    mfi = MfiAccount(
        name=payload.mfi_name,
        email=invite.email,
        plan_id=plan.id,
        status=MfiStatus.ACTIVE,
        billing_cycle_start=datetime.now(UTC).date().replace(day=1),
    )
    db.add(mfi)
    db.flush()

    manager = User(
        mfi_account_id=mfi.id,
        full_name=payload.full_name,
        email=invite.email,
        phone=payload.phone,
        hashed_pin=hash_password(payload.pin),
        role=AgentRole.MANAGER,
        status=AgentStatus.ACTIVE,
    )
    db.add(manager)
    invite.completed_at = datetime.now(UTC)
    db.flush()
    return CompleteResponse(email=invite.email)
