"""Preprocessing stage: decode and normalize raw image bytes.

The first pipeline step (Design doc §6.3.1). It turns the uploaded ID and
selfie bytes into clean BGR arrays that the OCR, liveness, and face stages
consume. OpenCV/NumPy are imported lazily so this module loads without the
optional ``ml`` extra.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.exceptions import ValidationError

if TYPE_CHECKING:
    import numpy as np

# Cap the longer image side to bound downstream OCR/face compute and memory.
MAX_DIMENSION = 1280

# CLAHE parameters for lighting normalization. A modest clip limit lifts
# shadowed NIC text without amplifying sensor noise on low-end phone photos.
CLAHE_CLIP_LIMIT = 2.0
CLAHE_TILE_GRID = (8, 8)

# Skews below this are left alone: sub-degree rotations are within the
# deskew estimator's own noise and re-warping would only blur the image.
MIN_SKEW_DEGREES = 0.5


def preprocess_image(
    data: bytes, *, max_dimension: int = MAX_DIMENSION
) -> np.ndarray:
    """Decode raw image bytes into a clean, normalized BGR array.

    Runs the Design doc §6.3.1 ``decode_and_preprocess`` steps in order:
    decode, downscale, normalize lighting, and deskew. The result is what
    the OCR, liveness, and face stages consume.

    Args:
        data: Raw bytes of an uploaded image (PNG/JPEG/…).
        max_dimension: Longest side, in pixels, to downscale to.

    Returns:
        A decoded ``(H, W, 3)`` BGR ``uint8`` array: downscaled if needed,
        contrast-normalized, and rotated upright.

    Raises:
        ValidationError: If the payload is empty or not a decodable image.
    """
    import cv2
    import numpy as np

    if not data:
        raise ValidationError("Empty image payload.")

    buffer = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
    if image is None:
        raise ValidationError("Unsupported or corrupt image data.")

    image = _downscale(image, max_dimension)
    image = _normalize_lighting(image)
    return _deskew(image)


def _downscale(image: np.ndarray, max_dimension: int) -> np.ndarray:
    """Scale ``image`` down so its longest side is ``max_dimension``.

    Images already within the bound are returned unchanged; only downscaling
    is performed (never upscaling), using area interpolation for quality.
    """
    import cv2

    height, width = image.shape[:2]
    longest = max(height, width)
    if longest <= max_dimension:
        return image

    scale = max_dimension / longest
    new_size = (round(width * scale), round(height * scale))
    return cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)


def _normalize_lighting(image: np.ndarray) -> np.ndarray:
    """Even out uneven lighting with CLAHE on the L channel.

    Works in LAB space so only luminance is equalized, leaving the colour
    channels untouched. This rescues text in shadow and glare without
    shifting the card's colours — key for the low-end-phone, poor-lighting
    field conditions called out in Design doc §Field-Condition Robustness.
    """
    import cv2

    lab = cv2.cvtColor(image, cv2.COLOR_BGR2LAB)
    lightness, a, b = cv2.split(lab)
    clahe = cv2.createCLAHE(
        clipLimit=CLAHE_CLIP_LIMIT, tileGridSize=CLAHE_TILE_GRID
    )
    lightness = clahe.apply(lightness)
    merged = cv2.merge((lightness, a, b))
    return cv2.cvtColor(merged, cv2.COLOR_LAB2BGR)


def _deskew(image: np.ndarray) -> np.ndarray:
    """Rotate ``image`` so its dominant content is axis-aligned.

    Estimates the skew from the minimum-area rectangle enclosing the
    foreground pixels, then rotates by that angle. Near-zero skews (below
    ``MIN_SKEW_DEGREES``) and blank images are returned unchanged.
    """
    import cv2

    angle = _skew_angle(image)
    if angle is None or abs(angle) < MIN_SKEW_DEGREES:
        return image

    height, width = image.shape[:2]
    center = (width / 2, height / 2)
    matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(
        image,
        matrix,
        (width, height),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )


def _skew_angle(image: np.ndarray) -> float | None:
    """Estimate the in-plane skew of ``image`` in degrees, or ``None``.

    Returns the rotation (in ``[-45, 45]``) that would make the foreground
    upright, or ``None`` when the image is blank and no angle can be found.
    """
    import cv2

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    _, mask = cv2.threshold(
        gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )
    coords = cv2.findNonZero(mask)
    if coords is None:
        return None

    # minAreaRect's angle wraps at 90°; fold it into [-45, 45] so we always
    # correct by the smallest rotation rather than tipping the card over.
    angle = cv2.minAreaRect(coords)[-1] % 90
    if angle > 45:
        angle -= 90
    return angle
