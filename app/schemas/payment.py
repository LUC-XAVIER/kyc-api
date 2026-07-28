"""Request/response schemas for subscription payments."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import PaymentProvider, PaymentStatus, PlanName


class SubscribeRequest(BaseModel):
    """Start a plan payment from the manager's mobile-money number."""

    plan: PlanName
    phone: str


class PaymentResponse(BaseModel):
    """A payment as the dashboard sees it (never any provider secret)."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    plan_name: PlanName
    amount: int
    currency: str
    phone: str
    status: PaymentStatus
    provider: PaymentProvider
    ussd_code: str | None
    failure_reason: str | None
    created_at: datetime
    completed_at: datetime | None
