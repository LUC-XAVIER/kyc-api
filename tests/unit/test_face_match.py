"""Unit tests for the face-matching stage.

The cosine-similarity maths is covered directly; the ArcFace path runs the
real DeepFace model, so it is guarded on the weights being present. Skipped
without OpenCV.
"""

import importlib.util
from pathlib import Path

import pytest

from app.pipeline.stages import face_match

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("cv2") is None,
    reason="requires the optional `ml` extra (OpenCV)",
)

_ARCFACE_WEIGHTS = Path.home() / ".deepface" / "weights" / "arcface_weights.h5"
_IDENTIFIERS = Path(__file__).parents[2] / "docs" / "Identifiers"
_NIC_V1 = _IDENTIFIERS / "NIC- Version1" / "front.png"
_NIC_V2 = _IDENTIFIERS / "NIC- Version2" / "cni-front.jpg"


def _arcface_ready() -> bool:
    """Whether DeepFace and the ArcFace weights are available."""
    return (
        importlib.util.find_spec("deepface") is not None
        and _ARCFACE_WEIGHTS.exists()
    )


def test_cosine_similarity_identical_is_one() -> None:
    """A vector is maximally similar to itself."""
    import numpy as np

    vector = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    assert face_match._cosine_similarity(vector, vector) == pytest.approx(1.0)


def test_cosine_similarity_orthogonal_is_zero() -> None:
    """Perpendicular vectors have zero similarity."""
    import numpy as np

    a = np.array([1.0, 0.0], dtype=np.float32)
    b = np.array([0.0, 1.0], dtype=np.float32)
    assert face_match._cosine_similarity(a, b) == pytest.approx(0.0)


def test_cosine_similarity_opposite_is_negative_one() -> None:
    """Anti-parallel vectors have similarity -1."""
    import numpy as np

    a = np.array([1.0, 1.0], dtype=np.float32)
    assert face_match._cosine_similarity(a, -a) == pytest.approx(-1.0)


def test_cosine_similarity_zero_vector_is_zero() -> None:
    """A zero-length vector yields 0, not a division error."""
    import numpy as np

    a = np.zeros(3, dtype=np.float32)
    b = np.ones(3, dtype=np.float32)
    assert face_match._cosine_similarity(a, b) == 0.0


@pytest.mark.skipif(
    not _arcface_ready() or not _NIC_V1.exists(),
    reason="requires DeepFace ArcFace weights and the reference images",
)
def test_arcface_embeds_and_discriminates() -> None:
    """ArcFace gives a 512-d embedding that separates different people."""
    from app.pipeline.stages import preprocess

    def portrait(path: Path) -> "object":
        front = preprocess.preprocess_image(path.read_bytes())
        return preprocess.crop_nic_zones(front).photo_zone

    v1 = portrait(_NIC_V1)
    v2 = portrait(_NIC_V2)
    embedding = face_match.represent_face(v1)

    assert embedding.shape == (512,)
    same = face_match._cosine_similarity(embedding, embedding)
    other = face_match._cosine_similarity(
        embedding, face_match.represent_face(v2)
    )
    assert same == pytest.approx(1.0, abs=1e-4)
    assert other < same  # different people are less similar than self


@pytest.mark.skipif(
    not _arcface_ready() or not _NIC_V1.exists(),
    reason="requires DeepFace ArcFace weights and the reference images",
)
def test_match_faces_verifies_same_portrait() -> None:
    """A portrait matches itself and yields a populated outcome."""
    from app.pipeline.stages import preprocess

    front = preprocess.preprocess_image(_NIC_V1.read_bytes())
    portrait = preprocess.crop_nic_zones(front).photo_zone

    outcome = face_match.match_faces(portrait, portrait)

    assert outcome.verified is True
    assert outcome.match_score == pytest.approx(1.0, abs=1e-4)
    assert outcome.threshold == face_match.DEFAULT_FACE_MATCH_THRESHOLD
