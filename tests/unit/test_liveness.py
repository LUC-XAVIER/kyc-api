"""Unit tests for the liveness stage.

The LBP feature extractor is deterministic and covered directly; the
MediaPipe no-face path is guarded on the optional ``ml`` extra. Skipped
entirely when OpenCV is absent.
"""

import importlib.util
from pathlib import Path

import pytest

from app.pipeline import face_detect
from app.pipeline.stages import liveness

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("cv2") is None,
    reason="requires the optional `ml` extra (OpenCV)",
)


def test_lbp_codes_uniform_region_sets_all_bits() -> None:
    """On a flat patch every neighbour ties the centre, so code is 255."""
    import numpy as np

    codes = liveness._lbp_codes(np.full((16, 16), 100, dtype=np.uint8))

    assert codes.shape == (16, 16)
    assert (codes == 255).all()


def test_lbp_codes_bright_centre_is_zero() -> None:
    """A centre brighter than all neighbours sets no bits."""
    import numpy as np

    patch = np.zeros((3, 3), dtype=np.uint8)
    patch[1, 1] = 255

    assert liveness._lbp_codes(patch)[1, 1] == 0


def test_extract_lbp_features_shape_and_norm() -> None:
    """The vector has the fixed length and is L2-normalized."""
    import numpy as np

    rng = np.random.default_rng(0)
    image = rng.integers(0, 255, size=(200, 200, 3), dtype=np.uint8)

    features = liveness.extract_lbp_features(image)

    assert features.shape == (16384,)  # (128/16)**2 * 256
    assert features.dtype == np.float32
    assert abs(float(np.linalg.norm(features)) - 1.0) < 1e-5


def test_extract_lbp_features_is_deterministic() -> None:
    """The same image always yields the same features (train/serve parity)."""
    import numpy as np

    rng = np.random.default_rng(1)
    image = rng.integers(0, 255, size=(150, 150, 3), dtype=np.uint8)

    assert np.array_equal(
        liveness.extract_lbp_features(image),
        liveness.extract_lbp_features(image),
    )


def test_extract_lbp_features_accepts_grayscale() -> None:
    """A 2-D grayscale image is handled like a colour one."""
    import numpy as np

    gray = np.random.default_rng(2).integers(
        0, 255, size=(128, 128), dtype=np.uint8
    )

    assert liveness.extract_lbp_features(gray).shape == (16384,)


def test_load_classifier_missing_model_raises(tmp_path: Path) -> None:
    """A missing model file fails with a clear, actionable error."""
    liveness._load_classifier.cache_clear()
    with pytest.raises(FileNotFoundError, match="train_antispoof"):
        liveness._load_classifier(tmp_path / "absent.joblib")


@pytest.mark.skipif(
    importlib.util.find_spec("mediapipe") is None
    or not face_detect.FACE_DETECTOR_MODEL_PATH.exists(),
    reason="requires MediaPipe and the fetched face-detector model",
)
def test_check_liveness_rejects_when_no_face() -> None:
    """A frame with no detectable face fails without loading the SVM."""
    import numpy as np

    blank = np.zeros((128, 128, 3), dtype=np.uint8)

    outcome = liveness.check_liveness(blank)

    assert outcome.passed is False
    assert outcome.score == 0.0
    assert outcome.method == "mediapipe+minifasnet"


# --- FasNet path (analyze mocked so no weights/torch are needed) ----------


class _FakeFasnet:
    """Stand-in for FasNet.Fasnet returning a canned (is_real, confidence)."""

    def __init__(self, is_real: bool, confidence: float) -> None:
        self._result = (is_real, confidence)

    def analyze(self, image, facial_area):  # noqa: ANN001, ANN201
        return self._result


@pytest.mark.parametrize(
    ("is_real", "confidence", "expected"),
    [
        (True, 0.99, 0.99),    # genuine -> P(live) is the confidence
        (False, 0.98, 0.02),   # spoof   -> P(live) is its complement
    ],
)
def test_antispoof_score_maps_to_p_live(
    monkeypatch, is_real: bool, confidence: float, expected: float
) -> None:
    """FasNet's (is_real, confidence) becomes a monotonic P(live)."""
    import numpy as np

    monkeypatch.setattr(
        liveness, "_fasnet", lambda: _FakeFasnet(is_real, confidence)
    )

    score = liveness._antispoof_score(
        np.zeros((10, 10, 3), dtype=np.uint8), (0, 0, 10, 10)
    )

    assert abs(score - expected) < 1e-6


def test_check_liveness_passes_genuine(monkeypatch) -> None:
    """A confident real score clears the threshold with the FasNet method."""
    import numpy as np

    monkeypatch.setattr(liveness, "detect_face_box", lambda img: (0, 0, 8, 8))
    monkeypatch.setattr(liveness, "_antispoof_score", lambda img, box: 0.999)

    outcome = liveness.check_liveness(np.zeros((8, 8, 3), dtype=np.uint8))

    assert outcome.passed is True
    assert outcome.score == 0.999
    assert outcome.method == "mediapipe+minifasnet"


def test_check_liveness_reviews_borderline(monkeypatch) -> None:
    """A mid-band score does not pass (routes to review downstream)."""
    import numpy as np

    monkeypatch.setattr(liveness, "detect_face_box", lambda img: (0, 0, 8, 8))
    monkeypatch.setattr(liveness, "_antispoof_score", lambda img, box: 0.45)

    outcome = liveness.check_liveness(np.zeros((8, 8, 3), dtype=np.uint8))

    assert outcome.passed is False
    assert outcome.score == 0.45
