"""Tests for the anti-spoof trainer and the full liveness inference path.

Verified synthetically: a separable toy dataset (smooth "live" vs noisy
"spoof" texture, which LBP tells apart) proves the trainer learns, and a
model trained on it drives check_liveness end to end on a real portrait.
Skipped without OpenCV; the inference test also needs MediaPipe + the
fetched face-detector model.
"""

import importlib.util
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("cv2") is None,
    reason="requires the optional `ml` extra (OpenCV)",
)

_IDENTIFIERS = Path(__file__).parents[2] / "docs" / "Identifiers"
_NIC_FRONT = _IDENTIFIERS / "NIC- Version1" / "front.png"

# Tiny grid, few folds, and low PCA rank so CV stays fast on toy data.
_SMALL_GRID = {"svc__C": [1, 10], "svc__gamma": ["scale"]}
_CV = 2
_PCA = 4


def _write_toy_dataset(root: Path, per_class: int = 8) -> None:
    """Populate ``root`` with smooth 'live' and noisy 'spoof' images."""
    import cv2
    import numpy as np

    rng = np.random.default_rng(0)
    (root / "live").mkdir(parents=True)
    (root / "spoof").mkdir(parents=True)
    for index in range(per_class):
        noise = rng.integers(0, 255, size=(128, 128, 3), dtype=np.uint8)
        smooth = cv2.GaussianBlur(noise, (21, 21), 0)  # low-texture "live"
        cv2.imwrite(str(root / "live" / f"{index}.png"), smooth)
        rough = rng.integers(0, 255, size=(128, 128, 3), dtype=np.uint8)
        cv2.imwrite(str(root / "spoof" / f"{index}.png"), rough)


def test_trainer_cross_validates_and_separates_classes(
    tmp_path: Path,
) -> None:
    """k-fold CV on the toy set selects a well-separating model."""
    from ml import train_antispoof

    _write_toy_dataset(tmp_path)
    features, labels = train_antispoof.load_dataset(tmp_path)
    model, report = train_antispoof.train_classifier(
        features, labels, cv=_CV, pca_components=_PCA, param_grid=_SMALL_GRID
    )

    assert features.shape[1] == 16384
    assert report["cv_score"] >= 0.75
    assert "svc__C" in report["best_params"]
    assert set(model.classes_) == {0, 1}


def test_evaluate_reports_test_metrics(tmp_path: Path) -> None:
    """Evaluate returns accuracy and ROC-AUC on a held-out set."""
    from ml import train_antispoof

    _write_toy_dataset(tmp_path / "train")
    _write_toy_dataset(tmp_path / "test", per_class=4)
    x_train, y_train = train_antispoof.load_dataset(tmp_path / "train")
    x_test, y_test = train_antispoof.load_dataset(tmp_path / "test")
    model, _ = train_antispoof.train_classifier(
        x_train, y_train, cv=_CV, pca_components=_PCA, param_grid=_SMALL_GRID
    )

    metrics = train_antispoof.evaluate(model, x_test, y_test)

    assert 0.0 <= metrics["accuracy"] <= 1.0
    assert 0.0 <= metrics["roc_auc"] <= 1.0


@pytest.mark.skipif(
    importlib.util.find_spec("mediapipe") is None or not _NIC_FRONT.exists(),
    reason="requires MediaPipe, the face model, and the reference image",
)
def test_liveness_inference_with_trained_model(tmp_path: Path) -> None:
    """A trained model drives the LBP fallback end to end on a real face."""
    import joblib

    from app.pipeline import face_detect
    from app.pipeline.stages import liveness, preprocess
    from ml import train_antispoof

    if not face_detect.FACE_DETECTOR_MODEL_PATH.exists():
        pytest.skip("face-detector model not fetched")

    _write_toy_dataset(tmp_path)
    features, labels = train_antispoof.load_dataset(tmp_path)
    model, _ = train_antispoof.train_classifier(
        features, labels, cv=_CV, pca_components=_PCA, param_grid=_SMALL_GRID
    )
    model_path = tmp_path / "model.joblib"
    joblib.dump(model, model_path)

    front = preprocess.preprocess_image(_NIC_FRONT.read_bytes())
    portrait = preprocess.crop_nic_zones(front).photo_zone

    outcome = liveness.check_liveness_lbp(portrait, model_path=model_path)

    assert isinstance(outcome.passed, bool)
    assert 0.0 <= outcome.score <= 1.0
    assert outcome.method == "mediapipe+lbp_svm"
