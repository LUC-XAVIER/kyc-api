"""Unit tests for the duplicate-detection stage.

Exercises the FAISS cosine index directly with synthetic embeddings — no
DeepFace or database needed. Skipped when FAISS is absent.
"""

import importlib.util

import pytest

from app.pipeline.stages import duplicate

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("faiss") is None,
    reason="requires the optional `ml` extra (FAISS)",
)


def _unit(*values: float) -> "object":
    """A small float32 vector for building deterministic embeddings."""
    import numpy as np

    return np.array(values, dtype=np.float32)


def test_empty_index_finds_no_duplicate() -> None:
    """Searching an empty index is a clean miss."""
    index = duplicate.FaceIndex(dim=3)

    outcome = index.search(_unit(1, 0, 0))

    assert outcome.is_duplicate is False
    assert outcome.similarity == 0.0
    assert outcome.matched_client_id is None


def test_identical_embedding_is_a_duplicate() -> None:
    """The same face scores ~1.0 and reports the matched client."""
    index = duplicate.FaceIndex(dim=3)
    index.add(_unit(1, 1, 0), client_id="CL-1")

    outcome = index.search(_unit(2, 2, 0))  # same direction, unnormalized

    assert outcome.is_duplicate is True
    assert outcome.similarity == pytest.approx(1.0, abs=1e-5)
    assert outcome.matched_client_id == "CL-1"


def test_orthogonal_embedding_is_not_a_duplicate() -> None:
    """An unrelated face scores ~0 and is not flagged."""
    index = duplicate.FaceIndex(dim=3)
    index.add(_unit(1, 0, 0), client_id="CL-1")

    outcome = index.search(_unit(0, 1, 0))

    assert outcome.is_duplicate is False
    assert outcome.similarity == pytest.approx(0.0, abs=1e-5)
    assert outcome.matched_client_id is None


def test_similarity_below_threshold_is_not_flagged() -> None:
    """A near miss under the threshold does not report a match."""
    index = duplicate.FaceIndex(dim=2)
    index.add(_unit(1, 0), client_id="CL-1")

    # cos(45°) ≈ 0.707, above default 0.6 — so raise the bar past it.
    outcome = index.search(_unit(1, 1), threshold=0.8)

    assert outcome.is_duplicate is False
    assert outcome.similarity == pytest.approx(0.7071, abs=1e-3)
    assert outcome.matched_client_id is None


def test_returns_nearest_of_several_clients() -> None:
    """The reported match is the most similar enrolled client."""
    index = duplicate.FaceIndex.from_embeddings(
        [("CL-1", _unit(1, 0, 0)), ("CL-2", _unit(0, 1, 0))],
        dim=3,
    )

    outcome = index.search(_unit(0, 1, 0.1))

    assert len(index) == 2
    assert outcome.is_duplicate is True
    assert outcome.matched_client_id == "CL-2"
