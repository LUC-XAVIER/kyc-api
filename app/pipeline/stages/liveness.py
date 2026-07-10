"""Liveness stage: two-layer anti-spoofing on the selfie.

Third pipeline step (Design doc §6.3.1). MediaPipe first confirms a real
face geometry is present, then DeepFace's pretrained **FasNet** (MiniFASNet)
deep anti-spoof CNN scores the selfie for print/replay spoofing. A selfie
must clear both to pass.

This supersedes the original LBP-texture SVM (Design doc §6.3.2), which
plateaued at ROC-AUC ~0.94 on the LCC-FASD proxy and rejected genuine users
at a security-first threshold. The deep model separates live from spoof far
better on real selfies; the LBP path is kept as :func:`check_liveness_lbp`
(a documented fallback), and its :func:`extract_lbp_features` remains shared
with the trainer ``ml/train_antispoof.py``. DeepFace/torch, OpenCV,
MediaPipe, scikit-learn, and joblib are imported lazily so this module loads
without the optional ``ml`` extra.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.pipeline.contracts import LivenessOutcome
from app.pipeline.face_detect import detect_face_box, face_present

if TYPE_CHECKING:
    import numpy as np

# Default LBP fallback model location, produced by ml/train_antispoof.py.
DEFAULT_MODEL_PATH = Path("ml/models/antispoof_lbp_svm.joblib")

# Minimum P(live) for the selfie to PASS anti-spoofing outright; scores below
# this but above the decision engine's review floor go to manual review rather
# than an outright reject. This is FasNet's threshold — it sits above the
# model's natural 0.5 real/spoof boundary for a security margin, and is
# PROVISIONAL until re-tuned on real selfies. See docs/ML-PIPELINE.md §4.
LIVENESS_THRESHOLD = 0.60

# Threshold for the legacy LBP-SVM fallback (kept from its LCC-FASD tuning,
# ≈5% attack-accept on that proxy set). See docs/ML-PIPELINE.md §4.2.
_LBP_THRESHOLD = 0.72

# Canonical face size and LBP cell size feeding the fixed-length feature
# vector: (128 / 16)**2 = 64 cells, each a 256-bin histogram -> 16384 dims.
_FACE_SIZE = 128
_CELL_SIZE = 16

# 8 neighbours in clockwise order from the top-left; bit i weights 2**i.
_LBP_OFFSETS = (
    (-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1),
)

_METHOD = "mediapipe+minifasnet"
_LBP_METHOD = "mediapipe+lbp_svm"


def check_liveness(
    selfie: np.ndarray, *, threshold: float = LIVENESS_THRESHOLD
) -> LivenessOutcome:
    """Run the two-layer liveness check on a preprocessed selfie.

    MediaPipe first confirms a face is present, then DeepFace's pretrained
    **FasNet** (MiniFASNet) deep anti-spoof CNN scores it. FasNet separates
    genuine from print/replay far better than the legacy LBP-SVM (which is
    kept as :func:`check_liveness_lbp`), so a real selfie clears the bar with
    margin instead of scraping the threshold.

    Args:
        selfie: Preprocessed BGR selfie array.
        threshold: Minimum P(live) for the anti-spoof layer to pass.

    Returns:
        A :class:`LivenessOutcome`; ``passed`` is False if no face geometry
        is found or the spoof score falls below ``threshold``.
    """
    box = detect_face_box(selfie)
    if box is None:
        return LivenessOutcome(passed=False, score=0.0, method=_METHOD)

    score = _antispoof_score(selfie, box)
    return LivenessOutcome(
        passed=score >= threshold, score=round(score, 4), method=_METHOD
    )


def _antispoof_score(
    image: np.ndarray, box: tuple[int, int, int, int]
) -> float:
    """P(live) in ``[0, 1]`` from FasNet over the detected face ``box``.

    FasNet returns ``(is_real, confidence)`` where ``confidence`` is the
    winning class's probability. Mapping it to a monotonic P(live) — the
    confidence when real, its complement when spoof — keeps the score
    comparable across cases for the pass/review thresholds.
    """
    is_real, confidence = _fasnet().analyze(image, box)
    return float(confidence if is_real else 1.0 - confidence)


@lru_cache(maxsize=1)
def _fasnet() -> Any:
    """Build and cache DeepFace's FasNet anti-spoof model.

    Weights auto-fetch to ``~/.deepface`` on first use.
    """
    from deepface.models.spoofing import FasNet

    return FasNet.Fasnet()


def check_liveness_lbp(
    selfie: np.ndarray,
    *,
    model_path: Path = DEFAULT_MODEL_PATH,
    threshold: float = _LBP_THRESHOLD,
) -> LivenessOutcome:
    """Legacy LBP-texture SVM anti-spoof, superseded by FasNet.

    Kept as a documented fallback / offline baseline (see
    docs/ML-PIPELINE.md §4); the LBP feature extractor is still shared with
    the trainer ``ml/train_antispoof.py``.
    """
    if not face_present(selfie):
        return LivenessOutcome(passed=False, score=0.0, method=_LBP_METHOD)

    classifier = _load_classifier(model_path)
    features = extract_lbp_features(selfie)
    score = float(classifier.predict_proba([features])[0][1])
    return LivenessOutcome(
        passed=score >= threshold, score=round(score, 4), method=_LBP_METHOD
    )


def extract_lbp_features(
    image: np.ndarray,
    *,
    face_size: int = _FACE_SIZE,
    cell_size: int = _CELL_SIZE,
) -> np.ndarray:
    """Extract a normalized LBP-histogram feature vector (Design §6.3.2).

    The face is grayscaled and resized to a canonical square, an 8-neighbour
    LBP code is computed per pixel, and each ``cell_size`` cell contributes a
    256-bin histogram. The concatenated histograms are L2-normalized so the
    vector is invariant to overall contrast — its length is fixed, which the
    SVM requires.

    Args:
        image: A BGR (or already-grayscale) face image.
        face_size: Canonical square size the face is resized to.
        cell_size: Side of each square LBP histogram cell.

    Returns:
        A 1-D ``float32`` feature vector of length
        ``(face_size / cell_size)**2 * 256``.
    """
    import cv2
    import numpy as np

    if image.ndim == 2:
        gray = image
    else:
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.resize(gray, (face_size, face_size))
    codes = _lbp_codes(gray)

    cells_per_side = face_size // cell_size
    histograms = []
    for row in range(cells_per_side):
        for col in range(cells_per_side):
            cell = codes[
                row * cell_size:(row + 1) * cell_size,
                col * cell_size:(col + 1) * cell_size,
            ]
            histogram = np.bincount(cell.ravel(), minlength=256)
            histograms.append(histogram)

    features = np.concatenate(histograms).astype(np.float32)
    norm = np.linalg.norm(features)
    if norm > 0:
        features /= norm
    return features


def _lbp_codes(gray: np.ndarray) -> np.ndarray:
    """Compute the 8-neighbour LBP code image, same shape as ``gray``.

    Each pixel's 8 neighbours are thresholded against it (``>=`` -> 1) and
    packed, most-significant bit first, into a ``uint8`` code. Borders use
    reflection so the code image keeps the input's dimensions.
    """
    import cv2
    import numpy as np

    padded = cv2.copyMakeBorder(gray, 1, 1, 1, 1, cv2.BORDER_REFLECT)
    height, width = gray.shape
    codes = np.zeros((height, width), dtype=np.uint8)
    for bit, (dy, dx) in enumerate(_LBP_OFFSETS):
        neighbor = padded[1 + dy:1 + dy + height, 1 + dx:1 + dx + width]
        codes |= ((neighbor >= gray) << bit).astype(np.uint8)
    return codes


@lru_cache(maxsize=4)
def _load_classifier(model_path: Path) -> Any:
    """Load and cache the trained LBP-SVM model.

    Raises:
        FileNotFoundError: If the model has not been trained yet.
    """
    import joblib

    if not model_path.exists():
        raise FileNotFoundError(
            f"Anti-spoof model not found at {model_path}. "
            "Train it with ml/train_antispoof.py."
        )
    return joblib.load(model_path)
