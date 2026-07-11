"""Response schema for the verification statistics endpoint.

Feeds the manager dashboard: KPI cards (totals, avg processing time), the
per-day stacked bars, the status donut, and the by-branch bars.
"""

from datetime import date

from pydantic import BaseModel


class DayBucket(BaseModel):
    """Per-day counts, grouped into the dashboard's three display bands."""

    date: date
    verified: int
    pending: int
    rejected: int


class BranchBucket(BaseModel):
    """Total verifications attributed to one branch in the period."""

    branch: str
    count: int


class VerificationStats(BaseModel):
    """Aggregated verification statistics for a period (and branch)."""

    period_start: date
    period_end: date
    total: int
    verified: int
    pending: int
    rejected: int
    by_status: dict[str, int]
    per_day: list[DayBucket]
    by_branch: list[BranchBucket]
    avg_processing_seconds: float | None
