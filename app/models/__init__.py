"""SQLAlchemy ORM entities (data layer).

Importing this package registers every model on ``Base.metadata`` so that
Alembic autogeneration and ``create_all`` see the full schema.
"""

from app.db.base import Base
from app.models.compliance import AuditLog, ComplianceReport
from app.models.mfi import Agent, ApiKey, MfiAccount, SubscriptionPlan
from app.models.onboarding import PinReset, SignupInvite
from app.models.verification import (
    DuplicateFlag,
    ExtractedData,
    FaceEmbedding,
    FaceMatchResult,
    LivenessResult,
    Verification,
)

__all__ = [
    "Base",
    "SubscriptionPlan",
    "MfiAccount",
    "Agent",
    "ApiKey",
    "Verification",
    "ExtractedData",
    "FaceEmbedding",
    "LivenessResult",
    "FaceMatchResult",
    "DuplicateFlag",
    "AuditLog",
    "ComplianceReport",
    "SignupInvite",
    "PinReset",
]
