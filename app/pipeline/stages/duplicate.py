"""Duplicate-detection stage: is this face enrolled under another client?

Fifth pipeline step (Design doc §6.3.1). The selfie's 512-d ArcFace
embedding (from :func:`app.pipeline.stages.face_match.represent_face`) is
searched against the embeddings already enrolled for the MFI. A FAISS
inner-product index over L2-normalized vectors makes each neighbour score a
cosine similarity; a hit at or above the threshold flags a potential
duplicate, which sends the verification to manual review (PENDING).

The index is an in-memory accelerator the caller builds from the persistent
pgvector store (``FaceEmbedding``), scoped to one MFI account and excluding
the querying client so a client never matches itself. FAISS/NumPy are
imported lazily so this module loads without the optional ``ml`` extra.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from app.pipeline.contracts import DuplicateOutcome

if TYPE_CHECKING:
    import numpy as np

EMBEDDING_DIM = 512

# Cosine similarity at or above which two faces are treated as the same
# person enrolled under different clients. Stricter than the face-match
# threshold — a duplicate should be a strong, unambiguous hit.
DEFAULT_DUPLICATE_THRESHOLD = 0.6


class FaceIndex:
    """A FAISS cosine-similarity index over enrolled face embeddings.

    Build it from the MFI's stored embeddings (excluding the querying
    client), then :meth:`search` the new selfie embedding against it.
    """

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        """Create an empty inner-product index of dimension ``dim``."""
        import faiss

        self._index = faiss.IndexFlatIP(dim)
        self._client_ids: list[str] = []

    @classmethod
    def from_embeddings(
        cls,
        items: Iterable[tuple[str, np.ndarray]],
        *,
        dim: int = EMBEDDING_DIM,
    ) -> FaceIndex:
        """Build an index from ``(client_id, embedding)`` pairs."""
        index = cls(dim)
        for client_id, embedding in items:
            index.add(embedding, client_id)
        return index

    def __len__(self) -> int:
        """Number of enrolled embeddings."""
        return self._index.ntotal

    def add(self, embedding: np.ndarray, client_id: str) -> None:
        """Enroll one ``embedding`` under ``client_id``."""
        self._index.add(_normalized(embedding)[None, :])
        self._client_ids.append(client_id)

    def search(
        self,
        embedding: np.ndarray,
        *,
        threshold: float = DEFAULT_DUPLICATE_THRESHOLD,
    ) -> DuplicateOutcome:
        """Find the nearest enrolled face and judge it against ``threshold``.

        Returns a :class:`DuplicateOutcome`; ``matched_client_id`` is set
        only when the nearest similarity clears the threshold.
        """
        if self._index.ntotal == 0:
            return DuplicateOutcome(is_duplicate=False, similarity=0.0)

        scores, positions = self._index.search(
            _normalized(embedding)[None, :], 1
        )
        similarity = float(scores[0][0])
        matched = self._client_ids[int(positions[0][0])]
        is_duplicate = similarity >= threshold
        return DuplicateOutcome(
            is_duplicate=is_duplicate,
            similarity=round(similarity, 4),
            matched_client_id=matched if is_duplicate else None,
        )


def _normalized(embedding: np.ndarray) -> np.ndarray:
    """Return ``embedding`` as an L2-normalized ``float32`` vector."""
    import numpy as np

    vector = np.asarray(embedding, dtype=np.float32)
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm else vector
