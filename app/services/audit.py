"""Audit-trail recording for compliance-relevant actions.

A thin helper that appends immutable :class:`AuditLog` rows. Callers record
who did what to which verification (Design doc: an immutable audit trail
over verification and review actions). Rows are only ever inserted, never
updated or deleted.
"""

import uuid

from sqlalchemy.orm import Session

from app.models import AuditLog
from app.models.enums import ActorType

# Canonical action strings, so queries and reports can group on them.
VERIFICATION_PROCESSED = "verification.processed"
REVIEW_APPROVED = "review.approved"
REVIEW_REJECTED = "review.rejected"


def record(
    db: Session,
    *,
    mfi_account_id: uuid.UUID,
    action: str,
    actor_type: ActorType,
    verification_id: uuid.UUID | None = None,
    actor_id: str | None = None,
    details: dict | None = None,
) -> None:
    """Append one audit-log entry (not committed here — the caller commits).

    Args:
        db: Request-scoped session.
        mfi_account_id: Owning tenant.
        action: A canonical action string (see the module constants).
        actor_type: Who acted (SYSTEM for the automated pipeline, MANAGER
            for a human review decision).
        verification_id: The verification the action concerns, if any.
        actor_id: Free-form identifier of the individual actor, if known.
        details: Extra JSON context (status, reason, …).
    """
    db.add(
        AuditLog(
            mfi_account_id=mfi_account_id,
            action=action,
            actor_type=actor_type,
            verification_id=verification_id,
            actor_id=actor_id,
            details=details,
        )
    )
