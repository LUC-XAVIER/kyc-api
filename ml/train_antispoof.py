"""Train the LBP-SVM anti-spoofing classifier (Design doc §6.3.2).

You provide two dataset directories — a training set and a test set — each
with one subfolder per class::

    <dir>/live/     genuine selfies
    <dir>/spoof/    print / replay attacks

Hyperparameters (SVM ``C`` / ``gamma``) are chosen by **k-fold
cross-validation** on the training set — the CV folds are the validation
signal, so no separate validation folder is needed. The test set is scored
once at the end for an unbiased estimate. Every image becomes an LBP
feature vector via the same :func:`extract_lbp_features` the liveness stage
uses at inference, keeping training and serving in lock-step.

Run from the repo root::

    python ml/train_antispoof.py \
        --train-dir data/antispoof/train --test-dir data/antispoof/test
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import cv2
import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.decomposition import PCA
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from app.pipeline.stages.liveness import (
    DEFAULT_MODEL_PATH,
    extract_lbp_features,
)

# Class subfolder names and their labels. Label 1 is "live" so the SVM's
# P(class 1) lines up with the liveness stage's P(live) score.
_CLASS_LABELS = {"spoof": 0, "live": 1}

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp"}

# PCA target dimensionality. The raw LBP vector is 16384-d, which makes an
# RBF kernel painfully slow; projecting to a compact subspace keeps the SVM
# tractable and denoises the histograms.
_PCA_COMPONENTS = 128

# Hyperparameter grid searched by cross-validation, addressing the SVM step
# of the pipeline. Kept modest so a run finishes in a minute or two.
_DEFAULT_PARAM_GRID = {
    "svc__C": [1, 10, 100],
    "svc__gamma": ["scale", 1e-2],
    "svc__kernel": ["rbf"],
}


def load_dataset(
    data_dir: Path,
    *,
    max_per_class: int | None = None,
    seed: int = 42,
) -> tuple[np.ndarray, np.ndarray]:
    """Load images under ``data_dir`` into feature and label arrays.

    Args:
        data_dir: Directory holding ``live/`` and ``spoof/`` subfolders.
        max_per_class: Cap on images loaded per class (a seeded random
            sample). ``None`` loads all — use the cap to keep the RBF-SVM
            tractable and to balance a skewed set.
        seed: Seed for the sampling draw.

    Returns:
        ``(features, labels)`` as arrays aligned by row.

    Raises:
        FileNotFoundError: If a class subfolder is missing.
        ValueError: If no readable images are found.
    """
    rng = np.random.default_rng(seed)
    features: list[np.ndarray] = []
    labels: list[int] = []
    for name, label in _CLASS_LABELS.items():
        class_dir = data_dir / name
        if not class_dir.is_dir():
            raise FileNotFoundError(f"Missing class folder: {class_dir}")
        paths = sorted(
            p for p in class_dir.iterdir()
            if p.suffix.lower() in _IMAGE_SUFFIXES
        )
        if max_per_class is not None and len(paths) > max_per_class:
            index = rng.choice(len(paths), max_per_class, replace=False)
            paths = [paths[i] for i in sorted(index)]
        for path in paths:
            image = cv2.imread(str(path))
            if image is None:
                continue
            features.append(extract_lbp_features(image))
            labels.append(label)

    if not features:
        raise ValueError(f"No readable images under {data_dir}.")
    return np.vstack(features), np.array(labels)


def _build_pipeline(pca_components: int) -> Pipeline:
    """Standardize, PCA-reduce, then classify with an RBF SVM."""
    return Pipeline(
        [
            ("scale", StandardScaler()),
            ("pca", PCA(n_components=pca_components, random_state=42)),
            ("svc", SVC(class_weight="balanced", random_state=42)),
        ]
    )


def train_classifier(
    features: np.ndarray,
    labels: np.ndarray,
    *,
    cv: int = 5,
    pca_components: int = _PCA_COMPONENTS,
    param_grid: dict[str, Any] | None = None,
    scoring: str = "roc_auc",
) -> tuple[CalibratedClassifierCV, dict[str, Any]]:
    """Select SVM hyperparameters by k-fold CV and fit a calibrated model.

    The estimator is a scale → PCA → SVM pipeline; PCA collapses the 16384-d
    LBP vector so the RBF kernel stays fast. The grid search runs over a
    plain SVM (ROC-AUC uses ``decision_function``, so no per-fit probability
    calibration — the slow part), then the winning pipeline is wrapped once
    in a :class:`CalibratedClassifierCV` to provide ``predict_proba`` without
    the deprecated ``SVC(probability=True)``.

    Args:
        features: Training feature matrix.
        labels: Training labels (0 spoof, 1 live).
        cv: Number of stratified cross-validation folds.
        pca_components: PCA output dimensionality.
        param_grid: Grid to search; defaults to :data:`_DEFAULT_PARAM_GRID`.
        scoring: CV scoring metric.

    Returns:
        The calibrated fitted classifier and a report with the winning CV
        score and hyperparameters.
    """
    search = GridSearchCV(
        _build_pipeline(pca_components),
        param_grid if param_grid is not None else _DEFAULT_PARAM_GRID,
        cv=cv,
        scoring=scoring,
    )
    search.fit(features, labels)

    best = _build_pipeline(pca_components).set_params(**search.best_params_)
    model = CalibratedClassifierCV(best, cv=cv, ensemble=False)
    model.fit(features, labels)

    report = {
        "cv_score": float(search.best_score_),
        "best_params": search.best_params_,
    }
    return model, report


def evaluate(
    model: CalibratedClassifierCV, features: np.ndarray, labels: np.ndarray
) -> dict[str, float]:
    """Score ``model`` on a held-out set (accuracy, and ROC-AUC if binary)."""
    metrics = {
        "accuracy": float(accuracy_score(labels, model.predict(features)))
    }
    if len(np.unique(labels)) == 2:
        proba = model.predict_proba(features)[:, 1]
        metrics["roc_auc"] = float(roc_auc_score(labels, proba))
    return metrics


def main() -> None:
    """Parse arguments, cross-validate, evaluate, and save the model."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--train-dir", type=Path, required=True, help="Training set root."
    )
    parser.add_argument(
        "--test-dir", type=Path, help="Test set root (scored once)."
    )
    parser.add_argument(
        "--output", type=Path, default=DEFAULT_MODEL_PATH, help="Model path."
    )
    parser.add_argument(
        "--cv", type=int, default=5, help="Cross-validation folds."
    )
    parser.add_argument(
        "--max-per-class", type=int, default=None,
        help="Cap training images per class (balances a skewed set).",
    )
    args = parser.parse_args()

    features, labels = load_dataset(
        args.train_dir, max_per_class=args.max_per_class
    )
    model, report = train_classifier(features, labels, cv=args.cv)
    print(
        f"Best CV {args.cv}-fold score: {report['cv_score']:.3f} "
        f"with {report['best_params']}"
    )

    if args.test_dir is not None:
        test_features, test_labels = load_dataset(args.test_dir)
        metrics = evaluate(model, test_features, test_labels)
        print("Held-out test metrics:", metrics)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, args.output)
    print(f"Saved model to {args.output}")


if __name__ == "__main__":
    main()
