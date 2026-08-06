"""The per-MFI client-ID uniqueness rule (retry allowed after a rejection)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session

from app.api.v1.routes.verify import _ensure_unique_client_id
from app.core.exceptions import ConflictError
from app.models import Verification
from app.models.enums import SubmissionMethod, VerificationStatus
from tests.factories import create_mfi_with_key


def _verification(
    db: Session, mfi_id, client_id: str, status: VerificationStatus
) -> None:
    db.add(
        Verification(
            client_id=client_id,
            mfi_account_id=mfi_id,
            submission_method=SubmissionMethod.API,
            status=status,
            processed_at=datetime.now(UTC),
        )
    )
    db.flush()


def test_rejected_id_can_be_reused(
    db_session: Session,
) -> None:
    """A REJECTED attempt frees its client ID for another try."""
    mfi, _ = create_mfi_with_key(db_session)
    _verification(db_session, mfi.id, "C-1", VerificationStatus.REJECTED)

    # Should not raise: the rejected attempt does not reserve the ID.
    _ensure_unique_client_id(db_session, mfi.id, "C-1")


@pytest.mark.parametrize(
    "status",
    [
        VerificationStatus.VERIFIED,
        VerificationStatus.APPROVED,
        VerificationStatus.PENDING,
    ],
)
def test_active_id_is_still_blocked(
    db_session: Session, status: VerificationStatus
) -> None:
    """A live (non-rejected) record still reserves the client ID."""
    mfi, _ = create_mfi_with_key(db_session)
    _verification(db_session, mfi.id, "C-2", status)

    with pytest.raises(ConflictError):
        _ensure_unique_client_id(db_session, mfi.id, "C-2")
