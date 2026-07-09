"""Unit tests for face-match score drift detection."""

import importlib.util

import pytest

from app.services import monitoring

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("evidently") is None,
    reason="requires the optional `ml` extra (Evidently)",
)


def test_detects_drift_between_shifted_distributions() -> None:
    """A clearly shifted score distribution is flagged as drift."""
    import numpy as np

    rng = np.random.default_rng(0)
    reference = rng.normal(0.8, 0.05, 200).clip(0, 1).tolist()
    current = rng.normal(0.4, 0.10, 200).clip(0, 1).tolist()

    outcome = monitoring.detect_drift(reference, current)

    assert outcome.drift_detected is True
    assert outcome.drift_score < monitoring.DRIFT_THRESHOLD


def test_no_drift_for_similar_distributions() -> None:
    """Two samples from the same distribution are not flagged."""
    import numpy as np

    rng = np.random.default_rng(1)
    reference = rng.normal(0.8, 0.05, 200).clip(0, 1).tolist()
    current = rng.normal(0.8, 0.05, 200).clip(0, 1).tolist()

    outcome = monitoring.detect_drift(reference, current)

    assert outcome.drift_detected is False
    assert outcome.drift_score >= monitoring.DRIFT_THRESHOLD
