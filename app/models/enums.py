"""Enumerations used across the ORM models.

Each value maps to a database ``ENUM`` type. String values are stored,
keeping the schema human-readable in compliance exports.
"""

import enum


class MfiStatus(enum.StrEnum):
    """Lifecycle state of a subscribing MFI account."""

    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"
    PENDING = "PENDING"


class AgentStatus(enum.StrEnum):
    """Lifecycle state of an MFI field-agent account."""

    ACTIVE = "ACTIVE"
    DISABLED = "DISABLED"


class AgentRole(enum.StrEnum):
    """Dashboard role of an MFI staff account (Design ActorType).

    Drives which dashboard surface the account sees and what it may do:
    an ``AGENT`` submits verifications; a ``MANAGER`` also reviews the
    pending queue and generates compliance reports. ``ADMIN`` is reserved
    for Openxtech platform staff.
    """

    AGENT = "AGENT"
    MANAGER = "MANAGER"
    ADMIN = "ADMIN"


class PlanName(enum.StrEnum):
    """The four subscription tiers (Design doc §6.2)."""

    STARTER = "STARTER"
    GROWTH = "GROWTH"
    PRO = "PRO"
    ENTERPRISE = "ENTERPRISE"


class SubmissionMethod(enum.StrEnum):
    """Channel through which a verification was submitted."""

    DASHBOARD = "DASHBOARD"
    API = "API"


class VerificationStatus(enum.StrEnum):
    """Final or interim status of a verification request."""

    VERIFIED = "VERIFIED"
    PENDING = "PENDING"
    REJECTED = "REJECTED"
    APPROVED = "APPROVED"  # set by a manager after reviewing a PENDING case


class Sex(enum.StrEnum):
    """Sex field extracted from the NIC."""

    M = "M"
    F = "F"


class DocumentType(enum.StrEnum):
    """Kind of identity document submitted for verification.

    Drives side handling and OCR parsing: a NIC splits its fields across a
    front and back, while a passport is single-page. Card generations (NIC
    v1 vs v2) are detected downstream, not distinguished here.
    """

    NIC = "NIC"
    PASSPORT = "PASSPORT"


class ActorType(enum.StrEnum):
    """Type of actor recorded in an audit-log entry."""

    AGENT = "AGENT"
    MANAGER = "MANAGER"
    ADMIN = "ADMIN"
    SYSTEM = "SYSTEM"


class DuplicateResolution(enum.StrEnum):
    """Manager decision on a flagged potential duplicate."""

    PENDING = "PENDING"
    CONFIRMED = "CONFIRMED"
    DISMISSED = "DISMISSED"


class ReportFormat(enum.StrEnum):
    """Output format of a generated compliance report."""

    PDF = "PDF"
