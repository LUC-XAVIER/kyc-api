"""Diagnose where OCR extraction breaks on a real document.

Runs the real pipeline stages on a front (and optional back) image and dumps
every intermediate artifact — preprocessed images, cropped zones, raw OCR
text per zone, MRZ localization + decode, parsed fields, and which required
field is missing — so we can see whether the failure is the crop, the OCR
engine, the MRZ, or the field parsing.

Run from the repo root::

    python scripts/ocr_debug.py \
        --front front.jpg --back back.jpg --doc-type NIC --out ocr_debug_out
"""

import argparse
from pathlib import Path

import cv2

from app.models.enums import DocumentType
from app.pipeline.stages import ocr, preprocess


def _save(out_dir: Path, name: str, image) -> None:
    """Write an intermediate image and note its path + shape."""
    path = out_dir / name
    cv2.imwrite(str(path), image)
    print(f"  saved {path}  shape={image.shape}")


def _dump_text(label: str, text: str) -> None:
    """Print the raw OCR text of a zone, line by line."""
    print(f"\n----- {label}: raw OCR -----")
    lines = [line for line in text.splitlines() if line.strip()]
    for line in lines:
        print(f"  | {line}")
    if not lines:
        print("  (empty)")


def _dump_fields(label: str, fields: dict) -> None:
    """Print the (value, confidence) parsed from a zone's text."""
    print(f"----- {label}: parsed fields -----")
    if not fields:
        print("  (nothing parsed)")
    for key, (value, confidence) in fields.items():
        print(f"  {key:16} = {value!r}   (conf {confidence})")


def main() -> None:
    """Parse arguments and dump the OCR pipeline's intermediate steps."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--front", type=Path, required=True)
    parser.add_argument("--back", type=Path)
    parser.add_argument(
        "--doc-type", choices=["NIC", "PASSPORT"], default="NIC"
    )
    parser.add_argument("--out", type=Path, default=Path("ocr_debug_out"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    doc_type = DocumentType(args.doc_type)

    print("=" * 70)
    print(f"OCR DEBUG — {args.doc_type}")
    print("=" * 70)

    front = preprocess.preprocess_image(args.front.read_bytes())
    _save(args.out, "01_front_preprocessed.png", front)
    zones = preprocess.crop_nic_zones(front)
    _save(args.out, "02_front_text_zone.png", zones.text_zone)
    _save(args.out, "03_front_photo_zone.png", zones.photo_zone)

    back = None
    if args.back is not None:
        back = preprocess.preprocess_image(args.back.read_bytes())
        _save(args.out, "04_back_preprocessed.png", back)

    # The region the OCR stage actually feeds on.
    front_region = (
        front if doc_type is DocumentType.PASSPORT else zones.text_zone
    )
    front_text = ocr._ocr_text(front_region)
    _dump_text("FRONT region", front_text)
    _dump_fields("FRONT region", ocr._parse_fields(front_text))

    if back is not None:
        back_text = ocr._ocr_text(back)
        _dump_text("BACK", back_text)
        _dump_fields("BACK", ocr._parse_fields(back_text))

    # PassportEye reads the MRZ from the RAW image (back for NIC, front for
    # passport) — our preprocessing wrecks its accuracy.
    mrz_path = args.front if doc_type is DocumentType.PASSPORT else args.back
    mrz_bytes = mrz_path.read_bytes() if mrz_path is not None else None
    if mrz_bytes is not None:
        print("\n----- MRZ (PassportEye) -----")
        mrz_fields = ocr.read_mrz_fields(mrz_bytes)
        if not mrz_fields:
            print("  (no valid MRZ read)")
        for key, (value, confidence) in mrz_fields.items():
            print(f"  {key:16} = {value!r}   (conf {confidence})")

    result = ocr.ocr_extract(
        front_region, doc_type, back_image=back, mrz_bytes=mrz_bytes
    )
    print("\n" + "=" * 70)
    print("FINAL OcrResult")
    print("=" * 70)
    for field in (
        "full_name", "id_number", "date_of_birth", "place_of_birth",
        "expiry_date", "sex", "occupation",
    ):
        print(f"  {field:16} = {getattr(result, field)!r}")
    print(f"  field_confidences = {result.field_confidences}")
    print(f"  success = {result.success}")

    missing = [
        field
        for field in ocr._REQUIRED_FIELDS
        if not getattr(result, field)
    ]
    verdict = "PASSED" if result.success else "FAILED (OCR_FAILED)"
    print(f"\n  required = {ocr._REQUIRED_FIELDS}")
    print(f"  missing  = {missing}  ->  OCR {verdict}")


if __name__ == "__main__":
    main()
