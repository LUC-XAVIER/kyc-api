"""Integration tests for the pgvector-backed duplicate store.

Exercises PgVectorDuplicateStore.build_index against the real database +
FAISS. Skipped when FAISS is absent.
"""

import importlib.util
from datetime import UTC, datetime

import numpy as np
import pytest
from sqlalchemy.orm import Session

from app.models import FaceEmbedding, Verification
from app.models.enums import SubmissionMethod, VerificationStatus
from app.services.duplicate_store import PgVectorDuplicateStore
from tests.factories import create_mfi_with_key

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("faiss") is None,
    reason="requires the optional `ml` extra (FAISS)",
)


def _enroll(db: Session, mfi_id, client_id: str, vector: np.ndarray) -> None:
    """Persist a VERIFIED verification and its face embedding."""
    verification = Verification(
        client_id=client_id,
        mfi_account_id=mfi_id,
        submission_method=SubmissionMethod.API,
        status=VerificationStatus.VERIFIED,
        processed_at=datetime.now(UTC),
    )
    db.add(verification)
    db.flush()
    db.add(
        FaceEmbedding(
            verification_id=verification.id,
            client_id=client_id,
            vector=vector.tolist(),
            model_used="ArcFace",
        )
    )
    db.flush()


def test_build_index_finds_enrolled_duplicate(db_session: Session) -> None:
    """The same face already enrolled is found as a duplicate."""
    account, _ = create_mfi_with_key(db_session, usage=0)
    face = np.ones(512, dtype=np.float32)
    _enroll(db_session, account.id, "CL-existing", face)

    index = PgVectorDuplicateStore(db_session).build_index(
        account.id, exclude_client_id="CL-new"
    )
    outcome = index.search(face)

    assert len(index) == 1
    assert outcome.is_duplicate is True
    assert outcome.matched_client_id == "CL-existing"


def test_build_index_excludes_querying_client(db_session: Session) -> None:
    """A client's own embedding is left out so it never self-matches."""
    account, _ = create_mfi_with_key(db_session, usage=0)
    _enroll(db_session, account.id, "CL-self", np.ones(512, dtype=np.float32))

    index = PgVectorDuplicateStore(db_session).build_index(
        account.id, exclude_client_id="CL-self"
    )

    assert len(index) == 0


def test_build_index_is_scoped_to_the_mfi(db_session: Session) -> None:
    """Another MFI's embeddings are not visible in the search."""
    account_a, _ = create_mfi_with_key(
        db_session, usage=0, email="a@example.com"
    )
    account_b, _ = create_mfi_with_key(
        db_session, usage=0, email="b@example.com"
    )
    _enroll(db_session, account_b.id, "CL-b", np.ones(512, dtype=np.float32))

    index = PgVectorDuplicateStore(db_session).build_index(
        account_a.id, exclude_client_id="CL-new"
    )

    assert len(index) == 0
