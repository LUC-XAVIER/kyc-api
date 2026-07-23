"""Schemas for the Openxtech platform-admin dashboard.

These are *cross-tenant*: they summarise every MFI on the platform, unlike
the per-tenant dashboard schemas. All are served behind
``require_platform_admin``.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.enums import AgentRole, AgentStatus, MfiStatus


class PlanBucket(BaseModel):
    """Number of MFIs subscribed to one plan (feeds the plan donut)."""

    plan: str
    count: int


class DayCount(BaseModel):
    """Total verifications across all MFIs on a single day."""

    date: date
    count: int


class QuotaRow(BaseModel):
    """One MFI's quota consumption, for the 'approaching limits' panel."""

    id: uuid.UUID
    name: str
    plan: str | None
    usage: int
    quota: int | None
    pct: int  # 0..100+, clamped for display on the client


class PlatformStats(BaseModel):
    """Platform-wide totals for the admin Overview screen."""

    total_mfis: int
    active_mfis: int
    suspended_mfis: int
    pending_mfis: int
    total_verifications: int
    total_users: int  # agents + managers (excludes platform admins)
    warning_count: int  # MFIs at or above 80% of their quota
    by_plan: list[PlanBucket]
    per_day: list[DayCount]  # last 14 days, all MFIs
    quota_rows: list[QuotaRow]  # highest consumption first


class AdminMfiSummary(BaseModel):
    """One MFI row in the admin accounts table."""

    id: uuid.UUID
    name: str
    email: str
    plan: str | None
    status: MfiStatus
    usage: int
    quota: int | None
    verifications: int
    users: int
    api_keys: int  # active keys
    branches: int
    created_at: datetime


class AdminApiKeySummary(BaseModel):
    """An MFI's API key as the admin sees it (never the secret)."""

    prefix: str
    is_active: bool
    last_used_at: datetime | None


class AdminAgentSummary(BaseModel):
    """One staff account under an MFI, with its verification count."""

    id: uuid.UUID
    full_name: str
    branch: str | None
    role: AgentRole
    status: AgentStatus
    verifications: int


class MfiPerformance(BaseModel):
    """Verification outcome breakdown for a single MFI."""

    verified: int
    pending: int
    rejected: int
    duplicates: int
    avg_processing_seconds: float | None


class AdminMfiDetail(BaseModel):
    """Full drill-down on one MFI for the admin detail screen."""

    id: uuid.UUID
    name: str
    email: str
    status: MfiStatus
    plan: str | None
    quota: int | None
    usage: int  # current billing-cycle usage
    max_branches: int | None
    max_agents: int | None
    api_access: bool
    this_month: int  # verifications in the current calendar month
    last_month: int
    avg_per_day: float
    billing_cycle_start: date | None
    created_at: datetime
    api_keys: list[AdminApiKeySummary]
    agents: list[AdminAgentSummary]
    performance: MfiPerformance


class MfiStatusUpdate(BaseModel):
    """Request to enable or disable an MFI account."""

    status: MfiStatus
