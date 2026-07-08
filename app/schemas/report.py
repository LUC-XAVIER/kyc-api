"""Request/response schemas for compliance reports."""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import ReportFormat


class ReportRequest(BaseModel):
    """Period a compliance report should cover (both dates inclusive)."""

    period_start: date
    period_end: date


class ReportSummary(BaseModel):
    """A generated compliance report."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    period_start: date
    period_end: date
    total_verifications: int
    status_breakdown: dict | None
    format: ReportFormat
    generated_at: datetime
