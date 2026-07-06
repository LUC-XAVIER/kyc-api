"""Unit tests for the image preprocessing stage.

Skipped entirely when the optional ``ml`` extra (OpenCV) is absent, so the
suite stays green on an API-only install.
"""

import importlib.util
from pathlib import Path

import pytest

from app.core.exceptions import ValidationError
from app.pipeline.stages import preprocess

# Real reference documents used to exercise Haar-based zone cropping.
_IDENTIFIERS = Path(__file__).parents[2] / "docs" / "Identifiers"
_ID_FRONTS = {
    "nic-v1": _IDENTIFIERS / "NIC- Version1" / "front.png",
    "nic-v2": _IDENTIFIERS / "NIC- Version2" / "cni-front.jpg",
    "passport": _IDENTIFIERS / "Passport" / "passport.png",
}

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("cv2") is None,
    reason="requires the optional `ml` extra (OpenCV)",
)


def _png_bytes(height: int, width: int) -> bytes:
    """Encode a blank BGR image of the given size as PNG bytes."""
    import cv2
    import numpy as np

    image = np.zeros((height, width, 3), dtype=np.uint8)
    ok, buffer = cv2.imencode(".png", image)
    assert ok
    return buffer.tobytes()


def test_decodes_a_valid_image() -> None:
    """A well-formed image decodes to an (H, W, 3) array of that size."""
    result = preprocess.preprocess_image(_png_bytes(10, 20))
    assert result.shape == (10, 20, 3)


def test_downscales_when_over_max_dimension() -> None:
    """An oversized image is scaled so its longest side hits the cap."""
    result = preprocess.preprocess_image(
        _png_bytes(2000, 1000), max_dimension=1280
    )
    assert max(result.shape[:2]) == 1280


def test_leaves_small_images_untouched() -> None:
    """Images within the cap are returned at their original size."""
    result = preprocess.preprocess_image(
        _png_bytes(100, 100), max_dimension=1280
    )
    assert result.shape == (100, 100, 3)


def test_rejects_empty_payload() -> None:
    """Empty bytes raise a ValidationError."""
    with pytest.raises(ValidationError):
        preprocess.preprocess_image(b"")


def test_rejects_non_image_bytes() -> None:
    """Undecodable bytes raise a ValidationError."""
    with pytest.raises(ValidationError):
        preprocess.preprocess_image(b"this is not an image")


def test_normalize_lighting_improves_low_contrast() -> None:
    """CLAHE widens the tonal range of a washed-out image."""
    import numpy as np

    # Textured detail crammed into a narrow mid-grey band, as a washed-out
    # phone photo would be. CLAHE stretches this local contrast back out.
    rng = np.random.default_rng(0)
    image = rng.integers(110, 130, size=(200, 200, 3), dtype=np.uint8)

    result = preprocess._normalize_lighting(image)

    assert result.shape == image.shape
    assert result.std() > image.std()


def test_deskew_straightens_a_rotated_image() -> None:
    """A rotated document is brought back to near-zero skew."""
    import cv2
    import numpy as np

    canvas = np.full((400, 600, 3), 255, dtype=np.uint8)
    cv2.rectangle(canvas, (150, 150), (450, 250), (0, 0, 0), -1)
    matrix = cv2.getRotationMatrix2D((300, 200), 10.0, 1.0)
    skewed = cv2.warpAffine(
        canvas, matrix, (600, 400), borderValue=(255, 255, 255)
    )

    result = preprocess._deskew(skewed)

    assert abs(preprocess._skew_angle(result)) < 1.0


def test_deskew_leaves_upright_image_unchanged() -> None:
    """An already-straight image is returned without rotation."""
    import cv2
    import numpy as np

    canvas = np.full((400, 600, 3), 255, dtype=np.uint8)
    cv2.rectangle(canvas, (150, 150), (450, 250), (0, 0, 0), -1)

    result = preprocess._deskew(canvas)

    assert np.array_equal(result, canvas)


@pytest.mark.parametrize(
    ("shape", "photo_box", "expected"),
    [
        # Photo on the right (NIC v1) -> text is the wide strip on the left.
        ((346, 516, 3), (322, 120, 180, 120), (0, 0, 322, 346)),
        # Photo on top (NIC v2) -> text is the tall strip below it.
        ((697, 440, 3), (90, 65, 300, 280), (0, 345, 440, 352)),
        # Photo on the left (passport) -> text is the strip on the right.
        ((433, 561, 3), (20, 95, 150, 150), (170, 0, 391, 433)),
    ],
)
def test_largest_complement_picks_the_text_side(
    shape: tuple[int, int, int],
    photo_box: tuple[int, int, int, int],
    expected: tuple[int, int, int, int],
) -> None:
    """Whichever side the photo is on, the text zone is the largest rest."""
    assert preprocess._largest_complement(shape, photo_box) == expected


@pytest.mark.parametrize("name", list(_ID_FRONTS))
def test_crop_nic_zones_on_reference_documents(name: str) -> None:
    """Each real ID front yields non-empty text and photo zones."""
    import cv2

    path = _ID_FRONTS[name]
    if not path.exists():
        pytest.skip(f"reference image missing: {path}")
    image = cv2.imread(str(path))

    zones = preprocess.crop_nic_zones(image)

    assert zones.text_zone.size > 0
    # The photo zone is a real crop, smaller than the whole document.
    full_area = image.shape[0] * image.shape[1]
    photo_area = zones.photo_zone.shape[0] * zones.photo_zone.shape[1]
    assert 0 < photo_area < full_area


def test_crop_nic_zones_without_a_portrait_raises() -> None:
    """A blank document with no detectable face is rejected."""
    import numpy as np

    blank = np.full((400, 600, 3), 255, dtype=np.uint8)
    with pytest.raises(ValidationError):
        preprocess.crop_nic_zones(blank)
