"""Unit tests for the shared MediaPipe face detector.

Runs the real BlazeFace model, so guarded on OpenCV + MediaPipe + the
fetched detector asset.
"""

import importlib.util
from pathlib import Path

import pytest

from app.pipeline import face_detect

_NIC_FRONT = (
    Path(__file__).parents[2]
    / "docs"
    / "Identifiers"
    / "NIC- Version1"
    / "front.png"
)

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("cv2") is None
    or importlib.util.find_spec("mediapipe") is None
    or not face_detect.FACE_DETECTOR_MODEL_PATH.exists()
    or not _NIC_FRONT.exists(),
    reason="requires OpenCV, MediaPipe, the detector model, and the image",
)


def _front():
    from app.pipeline.stages import preprocess

    return preprocess.preprocess_image(_NIC_FRONT.read_bytes())


def _blank():
    import numpy as np

    return np.zeros((128, 128, 3), dtype=np.uint8)


def test_detects_face_on_a_real_document() -> None:
    """The portrait on the ID front is detected."""
    assert face_detect.face_present(_front()) is True
    assert face_detect.detect_face_box(_front()) is not None


def test_no_face_on_a_blank_frame() -> None:
    """A blank frame reports no face."""
    assert face_detect.face_present(_blank()) is False
    assert face_detect.detect_face_box(_blank()) is None


def test_crop_face_returns_a_subregion() -> None:
    """The face crop is a real sub-region of the source image."""
    front = _front()
    crop = face_detect.crop_face(front)

    assert crop is not None
    full = front.shape[0] * front.shape[1]
    assert 0 < crop.shape[0] * crop.shape[1] < full


def test_crop_face_is_none_without_a_face() -> None:
    """A blank frame yields no crop."""
    assert face_detect.crop_face(_blank()) is None
