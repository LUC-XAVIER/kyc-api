"""pgvector-backed duplicate-face store for the verification pipeline.

Implements the read-only :class:`~app.pipeline.orchestrator.DuplicateStore`
port over the ``FaceEmbedding`` table: it loads an MFI's enrolled face
vectors (excluding the querying client) into a FAISS index for the pipeline
to search. Enrollment of new embeddings is the endpoint's job, not this
store's, so the pipeline stays side-effect free.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.models import FaceEmbedding, Verification
from app.pipeline.stages.duplicate import FaceIndex


class PgVectorDuplicateStore:
    """Builds a per-MFI FAISS search index from stored face embeddings."""

    def __init__(self, db: Session) -> None:
        """Bind the store to a request-scoped database session."""
        self._db = db

    def build_index(
        self, mfi_account_id: uuid.UUID, *, exclude_client_id: str
    ) -> FaceIndex:
        """Load the MFI's other clients' embeddings into a search index.

        Args:
            mfi_account_id: Tenant whose enrollments to search.
            exclude_client_id: The querying client, omitted so it never
                matches itself.

        Returns:
            A :class:`FaceIndex` over the matching embeddings.
        """
        import numpy as np

        rows = (
            self._db.query(FaceEmbedding.client_id, FaceEmbedding.vector)
            .join(
                Verification,
                FaceEmbedding.verification_id == Verification.id,
            )
            .filter(
                Verification.mfi_account_id == mfi_account_id,
                FaceEmbedding.client_id != exclude_client_id,
            )
            .all()
        )
        return FaceIndex.from_embeddings(
            (client_id, np.asarray(vector, dtype=np.float32))
            for client_id, vector in rows
        )
