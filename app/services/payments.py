"""Subscription-payment orchestration (plan checkout via mobile money).

Ties the payment gateway (:mod:`app.services.payment_provider`) to our data:
creates :class:`~app.models.payment.Payment` rows, polls or receives their
outcome, and — on success — activates or renews the MFI's subscription. All
state transitions are idempotent: a payment settles exactly once no matter
how many webhooks or polls arrive.
"""

import uuid
from datetime import UTC, date, datetime

from sqlalchemy.orm import Session

from app.core.exceptions import NotFoundError, ValidationError
from app.core.validation import normalize_cm_phone
from app.models import MfiAccount, Payment, SubscriptionPlan
from app.models.enums import (
    ActorType,
    MfiStatus,
    PaymentStatus,
    PlanName,
)
from app.services import audit
from app.services.payment_provider import StatusResult, get_provider


def _plan_or_400(db: Session, plan_name: PlanName) -> SubscriptionPlan:
    """Fetch a payable plan or reject (custom-priced plans can't self-pay)."""
    plan = (
        db.query(SubscriptionPlan).filter_by(name=plan_name).one_or_none()
    )
    if plan is None:
        raise NotFoundError("Unknown plan.")
    if plan.monthly_price is None:
        raise ValidationError(
            "This plan is custom-priced — contact sales to subscribe."
        )
    return plan


def start_subscription_payment(
    db: Session,
    *,
    mfi: MfiAccount,
    plan_name: PlanName,
    phone: str,
) -> Payment:
    """Begin a plan payment: create the record and prompt the payer.

    Args:
        db: Request-scoped session.
        mfi: The account being subscribed/renewed.
        plan_name: The tier being purchased.
        phone: The payer's mobile-money number (any local format).

    Returns:
        The created :class:`Payment` (PENDING), carrying the provider's
        reference and, when available, a USSD code to display.

    Raises:
        ValidationError: If the phone is invalid or the plan is custom-priced.
    """
    plan = _plan_or_400(db, plan_name)
    try:
        normalized = normalize_cm_phone(phone)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc

    provider = get_provider()
    external_reference = uuid.uuid4().hex
    payment = Payment(
        mfi_account_id=mfi.id,
        plan_name=plan_name,
        amount=plan.monthly_price,
        currency="XAF",
        phone=normalized,
        status=PaymentStatus.PENDING,
        provider=provider.name,
        external_reference=external_reference,
    )
    db.add(payment)
    db.flush()

    result = provider.initiate_collection(
        amount=plan.monthly_price,
        currency="XAF",
        # Campay wants bare international digits (no leading '+').
        phone=normalized.lstrip("+"),
        external_reference=external_reference,
        description=f"KYC-API {plan_name.value} plan — {mfi.name}",
    )
    payment.provider_reference = result.provider_reference
    payment.ussd_code = result.ussd_code
    audit.record(
        db,
        mfi_account_id=mfi.id,
        action=audit.PAYMENT_INITIATED,
        actor_type=ActorType.MANAGER,
        details={
            "plan": plan_name.value,
            "amount": plan.monthly_price,
            "reference": external_reference,
        },
    )
    db.commit()
    db.refresh(payment)
    return payment


def sync_payment_status(db: Session, payment: Payment) -> Payment:
    """Poll the provider and apply the outcome if it has settled.

    A no-op once the payment is already terminal, so it is safe to call from
    a client that polls repeatedly.
    """
    if payment.status is not PaymentStatus.PENDING:
        return payment
    provider = get_provider()
    result = provider.get_status(
        provider_reference=payment.provider_reference or "",
        phone=payment.phone,
    )
    if result.status is not PaymentStatus.PENDING:
        _settle(db, payment, result)
        db.commit()
        db.refresh(payment)
    return payment


def apply_webhook(
    db: Session,
    *,
    external_reference: str,
    status: PaymentStatus,
    provider_reference: str | None = None,
    failure_reason: str | None = None,
) -> Payment:
    """Apply a provider callback to its payment (idempotent).

    Raises:
        NotFoundError: If no payment matches the reference.
    """
    payment = (
        db.query(Payment)
        .filter_by(external_reference=external_reference)
        .one_or_none()
    )
    if payment is None:
        raise NotFoundError("Unknown payment reference.")
    # Already settled — a duplicate/late webhook must not re-activate or flip.
    if payment.status is PaymentStatus.PENDING:
        if provider_reference:
            payment.provider_reference = provider_reference
        _settle(
            db,
            payment,
            StatusResult(status=status, failure_reason=failure_reason),
        )
        db.commit()
        db.refresh(payment)
    return payment


def _settle(db: Session, payment: Payment, result: StatusResult) -> None:
    """Move a pending payment to its terminal state and act on it."""
    payment.status = result.status
    payment.completed_at = datetime.now(UTC)
    if result.status is PaymentStatus.SUCCESSFUL:
        _activate_subscription(db, payment)
        audit.record(
            db,
            mfi_account_id=payment.mfi_account_id,
            action=audit.PAYMENT_SUCCEEDED,
            actor_type=ActorType.SYSTEM,
            details={
                "plan": payment.plan_name.value,
                "amount": payment.amount,
                "reference": payment.external_reference,
            },
        )
    else:
        payment.failure_reason = result.failure_reason
        audit.record(
            db,
            mfi_account_id=payment.mfi_account_id,
            action=audit.PAYMENT_FAILED,
            actor_type=ActorType.SYSTEM,
            details={
                "reference": payment.external_reference,
                "reason": result.failure_reason,
            },
        )


def _activate_subscription(db: Session, payment: Payment) -> None:
    """Put the MFI on the paid plan and start a fresh billing cycle."""
    mfi = db.get(MfiAccount, payment.mfi_account_id)
    plan = (
        db.query(SubscriptionPlan)
        .filter_by(name=payment.plan_name)
        .one_or_none()
    )
    if mfi is None or plan is None:
        return
    mfi.plan_id = plan.id
    mfi.status = MfiStatus.ACTIVE
    mfi.billing_cycle_start = date.today()
    mfi.current_period_usage = 0
