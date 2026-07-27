"""Schemas for the platform-admin dashboard.

These are *cross-tenant*: they summarise every MFI on the platform, unlike
the per-tenant dashboard schemas. All are served behind
``require_platform_admin``.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.enums import ActorType, AgentRole, AgentStatus, MfiStatus


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


class ScoreBucket(BaseModel):
    """One bar of a 0.0–1.0 score histogram."""

    label: str
    count: int


class PerMfiScore(BaseModel):
    """A single MFI's aggregate model scores (to spot weak populations)."""

    name: str
    evaluated: int
    avg_score: float | None
    verified_rate: float | None  # fraction 0..1


class FaceMatchingReport(BaseModel):
    """Cross-tenant face-match metrics from stored results."""

    evaluated: int
    avg_score: float | None
    threshold: float | None
    verified_rate: float | None
    distribution: list[ScoreBucket]
    per_mfi: list[PerMfiScore]


class AntiSpoofReport(BaseModel):
    """Cross-tenant liveness / anti-spoof metrics from stored results."""

    evaluated: int
    avg_score: float | None
    pass_rate: float | None
    spoof_flagged: int
    distribution: list[ScoreBucket]


class OcrFieldAccuracy(BaseModel):
    """Average OCR confidence for one NIC field."""

    field: str
    avg_confidence: float
    samples: int


class OcrReport(BaseModel):
    """Cross-tenant OCR confidence, aggregated from field_confidences."""

    evaluated: int
    avg_confidence: float | None
    per_field: list[OcrFieldAccuracy]


class DuplicateReport(BaseModel):
    """Duplicate-detector footprint and flag outcomes."""

    index_size: int  # stored face embeddings
    flags: int
    avg_similarity: float | None
    confirmed: int
    dismissed: int
    pending: int


class ModelHealthReport(BaseModel):
    """Everything the model-monitoring screens render, all real data."""

    face_matching: FaceMatchingReport
    anti_spoofing: AntiSpoofReport
    ocr: OcrReport
    duplicate: DuplicateReport


class LatencyStats(BaseModel):
    """End-to-end pipeline processing time (not HTTP latency)."""

    measured: int
    avg_seconds: float | None
    p50_seconds: float | None
    p95_seconds: float | None
    max_seconds: float | None


class ChannelCount(BaseModel):
    """Verification volume by submission channel (API vs dashboard)."""

    channel: str
    count: int


class OperationsReport(BaseModel):
    """Real operational figures for the System Health / API screens.

    Everything here is queried from our own tables — infra metrics (uptime,
    CPU, container health, per-endpoint HTTP latency) are not collected, so
    they are simply absent rather than invented.
    """

    total_verifications: int
    total_embeddings: int
    total_users: int
    total_mfis: int
    total_api_keys: int
    latency: LatencyStats
    per_day: list[DayCount]
    by_channel: list[ChannelCount]


class AdminAuditEntry(BaseModel):
    """One immutable audit-log row, with its MFI resolved to a name."""

    id: uuid.UUID
    action: str
    actor_type: ActorType
    actor_id: str | None
    mfi_name: str | None
    verification_id: uuid.UUID | None
    details: dict | None
    timestamp: datetime
