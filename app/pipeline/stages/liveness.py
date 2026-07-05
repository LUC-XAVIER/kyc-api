"""Liveness stage: two-layer anti-spoofing on the selfie.

Third pipeline step (Design doc §6.3.1). MediaPipe first confirms a real
face geometry is present, then an LBP-texture SVM (Design doc §6.3.2)
scores the selfie for print/replay spoofing. A selfie must clear both to
pass.

:func:`extract_lbp_features` is the feature extractor shared with the
offline trainer (``ml/train_antispoof.py``) — importing the one
implementation keeps training and inference in lock-step. OpenCV,
MediaPipe, scikit-learn, and joblib are imported lazily so this module
loads without the optional ``ml`` extra.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.pipeline.contracts import LivenessOutcome

if TYPE_CHECKING:
    import numpy as np

# Default trained-model location, produced by ml/train_antispoof.py.
DEFAULT_MODEL_PATH = Path("ml/models/antispoof_lbp_svm.joblib")

# MediaPipe face-detector asset (BlazeFace short-range). Fetch once from
# https://storage.googleapis.com/mediapipe-models/face_detector/
# blaze_face_short_range/float16/1/blaze_face_short_range.tflite
FACE_DETECTOR_MODEL_PATH = Path("ml/models/blaze_face_short_range.tflite")

# Minimum P(live) from the SVM for the selfie to pass anti-spoofing.
LIVENESS_THRESHOLD = 0.5

# Canonical face size and LBP cell size feeding the fixed-length feature
# vector: (128 / 16)**2 = 64 cells, each a 256-bin histogram -> 16384 dims.
_FACE_SIZE = 128
_CELL_SIZE = 16

# 8 neighbours in clockwise order from the top-left; bit i weights 2**i.
_LBP_OFFSETS = (
    (-1, -1), (-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1),
)

_METHOD = "mediapipe+lbp_svm"


def check_liveness(
    selfie: np.ndarray,
    *,
    model_path: Path = DEFAULT_MODEL_PATH,
    threshold: float = LIVENESS_THRESHOLD,
) -> LivenessOutcome:
    """Run the two-layer liveness check on a preprocessed selfie.

    Args:
        selfie: Preprocessed BGR selfie array.
        model_path: Path to the trained LBP-SVM joblib model.
        threshold: Minimum P(live) for the anti-spoof layer to pass.

    Returns:
        A :class:`LivenessOutcome`; ``passed`` is False if no face geometry
        is found or the spoof score falls below ``threshold``.
    """
    if not _face_present(selfie):
        return LivenessOutcome(passed=False, score=0.0, method=_METHOD)

    classifier = _load_classifier(model_path)
    features = extract_lbp_features(selfie)
    score = float(classifier.predict_proba([features])[0][1])
    return LivenessOutcome(
        passed=score >= threshold, score=round(score, 4), method=_METHOD
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


def _face_present(image: np.ndarray) -> bool:
    """Whether MediaPipe detects a face (with keypoints) in ``image``."""
    import cv2
    import mediapipe as mp

    detector = _face_detector(FACE_DETECTOR_MODEL_PATH)
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    return bool(detector.detect(mp_image).detections)


@lru_cache(maxsize=1)
def _face_detector(model_path: Path) -> Any:
    """Build and cache the MediaPipe BlazeFace detector.

    Raises:
        FileNotFoundError: If the detector asset has not been fetched.
    """
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision

    if not model_path.exists():
        raise FileNotFoundError(
            f"Face-detector model not found at {model_path}. See the "
            "FACE_DETECTOR_MODEL_PATH comment for the download URL."
        )
    options = vision.FaceDetectorOptions(
        base_options=python.BaseOptions(model_asset_path=str(model_path)),
        min_detection_confidence=0.5,
    )
    return vision.FaceDetector.create_from_options(options)


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
