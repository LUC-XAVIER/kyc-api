"""SQLAlchemy ORM entities (data layer).

Importing this package registers every model on ``Base.metadata`` so that
Alembic autogeneration and ``create_all`` see the full schema.
"""

from app.db.base import Base
from app.models.compliance import AuditLog, ComplianceReport
from app.models.mfi import (
    ApiKey,
    Branch,
    MfiAccount,
    SubscriptionPlan,
    User,
)
from app.models.onboarding import PinReset, SignupInvite
from app.models.verification import (
    DuplicateFlag,
    ExtractedData,
    FaceEmbedding,
    FaceMatchResult,
    LivenessResult,
    Verification,
    VerificationImage,
)

__all__ = [
    "Base",
    "SubscriptionPlan",
    "MfiAccount",
    "User",
    "Branch",
    "ApiKey",
    "Verification",
    "VerificationImage",
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
