"""Subscription-payment routes (mobile money via Campay).

A manager starts a plan payment for their own MFI, then polls it to
completion; the provider also confirms out-of-band via the webhook. The
webhook is unauthenticated by bearer/key — it is verified instead by the
provider's request signature.
"""

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.api.v1.deps import Principal, require_manager_principal
from app.core.exceptions import NotFoundError
from app.db.session import get_db
from app.models import Payment
from app.models.enums import PaymentStatus
from app.schemas.payment import PaymentResponse, SubscribeRequest
from app.services import payments as payment_service
from app.services.payment_provider import get_provider

router = APIRouter(prefix="/payments", tags=["payments"])

# Campay webhook status strings → our enum.
_WEBHOOK_STATUS = {
    "SUCCESSFUL": PaymentStatus.SUCCESSFUL,
    "FAILED": PaymentStatus.FAILED,
    "PENDING": PaymentStatus.PENDING,
}


@router.post("/subscribe", response_model=PaymentResponse)
def subscribe(
    payload: SubscribeRequest,
    principal: Principal = Depends(require_manager_principal),
    db: Session = Depends(get_db),
) -> Payment:
    """Start a plan payment for the caller's MFI (prompts their phone)."""
    return payment_service.start_subscription_payment(
        db,
        mfi=principal.mfi_account,
        plan_name=payload.plan,
        phone=payload.phone,
    )


@router.get("", response_model=list[PaymentResponse])
def list_payments(
    principal: Principal = Depends(require_manager_principal),
    db: Session = Depends(get_db),
) -> list[Payment]:
    """List the MFI's payments, newest first."""
    return (
        db.query(Payment)
        .filter_by(mfi_account_id=principal.mfi_account.id)
        .order_by(Payment.created_at.desc())
        .all()
    )


@router.get("/{payment_id}", response_model=PaymentResponse)
def get_payment(
    payment_id: uuid.UUID,
    principal: Principal = Depends(require_manager_principal),
    db: Session = Depends(get_db),
) -> Payment:
    """Fetch one payment (scoped to the MFI), polling the provider first."""
    payment = (
        db.query(Payment)
        .filter_by(id=payment_id, mfi_account_id=principal.mfi_account.id)
        .one_or_none()
    )
    if payment is None:
        raise NotFoundError("Payment not found.")
    return payment_service.sync_payment_status(db, payment)


@router.post("/webhook", status_code=200)
async def webhook(
    request: Request, db: Session = Depends(get_db)
) -> dict[str, str]:
    """Receive a provider payment-status callback.

    Unauthenticated by design (the provider has no bearer token); instead
    the request signature is verified before anything is applied. An invalid
    or unknown callback is acknowledged with 200 but ignored, so the
    provider does not retry a request we will never accept.
    """
    params = await _read_params(request)
    provider = get_provider()
    if not provider.verify_webhook(params):
        return {"status": "ignored"}

    reference = params.get("external_reference")
    status = _WEBHOOK_STATUS.get(params.get("status", ""))
    if not reference or status is None:
        return {"status": "ignored"}
    try:
        payment_service.apply_webhook(
            db,
            external_reference=reference,
            status=status,
            provider_reference=params.get("reference"),
            failure_reason=params.get("reason"),
        )
    except NotFoundError:
        return {"status": "ignored"}
    return {"status": "ok"}


async def _read_params(request: Request) -> dict[str, str]:
    """Parse the callback body as JSON or form data, whichever was sent."""
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            return await request.json()
        except ValueError:
            return {}
    form = await request.form()
    return {k: str(v) for k, v in form.items()}
