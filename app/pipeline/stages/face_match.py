"""Face-matching stage: compare the selfie to the NIC portrait.

Fourth pipeline step (Design doc §6.3.1). DeepFace's ArcFace backend embeds
each face into a 512-d vector; the cosine similarity between the selfie and
the NIC portrait is scored against a tunable threshold. The same
:func:`represent_face` embedding is what the duplicate stage stores and
searches, so identity comparison and duplicate detection stay consistent.

DeepFace/TensorFlow are imported lazily so this module loads without the
optional ``ml`` extra.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.pipeline.contracts import FaceMatchOutcome

if TYPE_CHECKING:
    import numpy as np

# DeepFace backend. "opencv" detection (bundled Haar) + alignment runs
# in-process with no extra model download; enforce_detection is off so a
# tight crop that the detector misses still falls back to the whole image.
_MODEL_NAME = "ArcFace"
_DETECTOR_BACKEND = "opencv"

# Cosine-similarity floor for the selfie and portrait to be the same person.
# ArcFace separates identities well above this; tune on real selfie/ID pairs.
DEFAULT_FACE_MATCH_THRESHOLD = 0.40


def match_faces(
    selfie: np.ndarray,
    portrait: np.ndarray,
    *,
    threshold: float = DEFAULT_FACE_MATCH_THRESHOLD,
) -> FaceMatchOutcome:
    """Compare a selfie to the ID portrait with ArcFace.

    Args:
        selfie: Preprocessed BGR selfie array.
        portrait: The NIC ``photo_zone`` crop from :func:`crop_nic_zones`.
        threshold: Minimum cosine similarity to count as a match.

    Returns:
        A :class:`FaceMatchOutcome` with the similarity, the verdict, and
        the threshold used.
    """
    similarity = _cosine_similarity(
        represent_face(selfie), represent_face(portrait)
    )
    return FaceMatchOutcome(
        match_score=round(float(similarity), 4),
        verified=bool(similarity >= threshold),
        threshold=threshold,
    )


def represent_face(image: np.ndarray) -> np.ndarray:
    """Embed the face in ``image`` into a 512-d ArcFace vector."""
    import numpy as np
    from deepface import DeepFace

    representations = DeepFace.represent(
        img_path=image,
        model_name=_MODEL_NAME,
        detector_backend=_DETECTOR_BACKEND,
        enforce_detection=False,
    )
    return np.asarray(representations[0]["embedding"], dtype=np.float32)


def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity of two vectors, ``0.0`` if either is zero-length."""
    import numpy as np

    denominator = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denominator == 0.0:
        return 0.0
    return float(np.dot(a, b) / denominator)
