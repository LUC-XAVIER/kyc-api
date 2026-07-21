"""Re-compress captured images before they are stored for manager review.

The originals arrive at whatever resolution the phone camera produced (often
several megabytes). We keep a JPEG that is small enough not to bloat the
database yet still legible for a human to eyeball the document and the face.
The stored bytes are sealed at rest by :class:`app.db.types.EncryptedBytes`.
"""

import io

from PIL import Image, ImageOps

# A NIC's small print stays readable at ~1280px on the long edge, and a
# quality-80 JPEG is visually clean while a fraction of the original size.
MAX_DIMENSION = 1280
JPEG_QUALITY = 80


def compress_to_jpeg(
    raw: bytes,
    *,
    max_dimension: int = MAX_DIMENSION,
    quality: int = JPEG_QUALITY,
) -> bytes:
    """Return ``raw`` re-encoded as a downscaled JPEG.

    Honours the camera's EXIF orientation (so portrait shots aren't stored
    sideways), flattens any alpha onto white, and never upscales.
    """
    with Image.open(io.BytesIO(raw)) as img:
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.thumbnail((max_dimension, max_dimension))
        out = io.BytesIO()
        img.save(out, format="JPEG", quality=quality, optimize=True)
        return out.getvalue()
