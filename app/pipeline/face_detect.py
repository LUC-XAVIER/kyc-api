"""Shared MediaPipe face detection for the liveness and face-match stages.

One BlazeFace detector serves both the liveness presence check and the
face-match embedding, so a face found by one stage is the same region the
other operates on (Design doc: "Extracts face regions using MediaPipe").
This avoids the earlier split where liveness used MediaPipe but face
embedding used a different detector and silently fell back to the whole
frame. MediaPipe/OpenCV are imported lazily.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import numpy as np

# BlazeFace short-range asset. Fetch once from
# https://storage.googleapis.com/mediapipe-models/face_detector/
# blaze_face_short_range/float16/1/blaze_face_short_range.tflite
FACE_DETECTOR_MODEL_PATH = Path("ml/models/blaze_face_short_range.tflite")

# Padding added around a detected face box when cropping, so the crop keeps
# hair, chin, and a little margin the embedder benefits from.
_FACE_CROP_PAD = 0.25


def detect_face_box(image: np.ndarray) -> tuple[int, int, int, int] | None:
    """Return the largest detected face box ``(x, y, w, h)``, or ``None``."""
    import cv2
    import mediapipe as mp

    detector = _detector(FACE_DETECTOR_MODEL_PATH)
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    detections = detector.detect(mp_image).detections
    if not detections:
        return None
    box = max(
        (d.bounding_box for d in detections),
        key=lambda b: b.width * b.height,
    )
    return box.origin_x, box.origin_y, box.width, box.height


def face_present(image: np.ndarray) -> bool:
    """Whether MediaPipe detects a face in ``image``."""
    return detect_face_box(image) is not None


def crop_face(
    image: np.ndarray, *, pad_ratio: float = _FACE_CROP_PAD
) -> np.ndarray | None:
    """Crop the largest detected face (padded), or ``None`` if none found."""
    box = detect_face_box(image)
    if box is None:
        return None
    x, y, width, height = box
    pad_x, pad_y = int(width * pad_ratio), int(height * pad_ratio)
    img_h, img_w = image.shape[:2]
    x0, y0 = max(0, x - pad_x), max(0, y - pad_y)
    x1 = min(img_w, x + width + pad_x)
    y1 = min(img_h, y + height + pad_y)
    return image[y0:y1, x0:x1]


@lru_cache(maxsize=1)
def _detector(model_path: Path) -> Any:
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
