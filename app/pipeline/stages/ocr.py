"""OCR stage: extract identity fields from a document's text zones.

Second pipeline step (Design doc §6.3.1). Runs Tesseract over the cropped
text zone(s) and parses the raw text into a structured :class:`OcrResult`
with per-field confidences.

Parsing branches on the document type and, for NIC cards, MERGES fields
split across the front and back: NIC v1 keeps the expiry date and ID number
on the back, NIC v2 the place of birth and occupation. The machine-readable
zone (MRZ) on the NIC v2 back and on the passport is checksummed, so a
value read from a check-digit-valid MRZ outranks the same field read from
the visual text.

Tesseract/OpenCV are imported lazily so this module loads without the
optional ``ml`` extra.
"""

from __future__ import annotations

import re
from datetime import date
from typing import TYPE_CHECKING, Any

from app.models.enums import DocumentType, Sex
from app.pipeline.contracts import OcrResult

if TYPE_CHECKING:
    from collections.abc import Callable

    import numpy as np

# Confidence assigned by source. An MRZ field is trusted more than the same
# value read from the printed text because its check digit is validated.
_VISUAL_CONFIDENCE = 0.75
_MRZ_CONFIDENCE = 0.98

# Minimum PassportEye validity score (0-100, ~25 per passing check digit) to
# trust an MRZ read at all; below this we fall back to the visual OCR.
_MIN_MRZ_SCORE = 50

# Fields that must all resolve for the extraction to count as a success.
_REQUIRED_FIELDS = ("full_name", "id_number", "expiry_date")

# A single parsed field carries its value and the confidence of its source.
_Field = tuple[Any, float]
_Fields = dict[str, _Field]

def _bilingual(french: str, english: str) -> str:
    """Build a label regex that consumes the whole ``FR/EN`` header.

    The cards print both languages ("LIEU DE NAISSANCE/PLACE OF BIRTH"), so
    matching only one side would leave the other stuck in the value.
    """
    return rf"{french}(?:\s*[/·]?\s*{english})?|{english}"


# Bilingual (FR/EN) labels printed beside each value on the cards. Spaces
# between words are optional (``\s*``) because OCR routinely fuses them.
_SURNAME_LABEL = _bilingual(r"NOMS?", r"SURNAME")
_GIVEN_LABEL = _bilingual(r"PR[EÉ]NOMS?", r"GIVEN\s*NAMES?")
_DOB_LABEL = _bilingual(r"DATE\s*DE\s*NAISSANCE", r"DATE\s*OF\s*BIRTH")
_POB_LABEL = _bilingual(r"LIEU\s*DE\s*NAISSANCE", r"PLACE\s*OF\s*BIRTH")
_EXPIRY_LABEL = _bilingual(
    r"DATE\s*D[’'`]?EXPIRATION", r"DATE\s*OF\s*EXPIRY"
)
_SEX_LABEL = _bilingual(r"SEXE?", r"SEX")
_OCCUPATION_LABEL = _bilingual(r"PROFESSION", r"OCCUPATION")
_ID_LABEL = "|".join(
    (
        _bilingual(r"NUM[EÉ]RO\s*CNI", r"NIC\s*NUMBER"),
        _bilingual(
            r"NUM[EÉ]RO\s*D[’'`]?IDENTIFICATION", r"IDENTIFICATION\s*NUMBER"
        ),
        _bilingual(r"N[°o]\s*D[’'`]?IDENTIFICATION", r"ID\s*N[o.]"),
        r"PASSE?PORT\s*N[°o]?",
    )
)

# A date printed as DD.MM.YYYY (NIC) or DD MM YYYY (passport); tolerant of
# '/', '-' and OCR spacing between the parts.
_DATE_RE = re.compile(r"(\d{1,2})\s*[.\s/\-]\s*(\d{1,2})\s*[.\s/\-]\s*(\d{4})")

# The first run of ALL-CAPS words (≥3 chars), the shape of a printed name /
# place / occupation. Lets us skip the mixed-case guilloche speckle that OCR
# picks up beside a label ("joa id hn See", "NA = ee ae") and reach the real
# uppercase value on the next line ("LIMBE", "ETUDIANT").
_UPPER_VALUE_RE = re.compile(
    r"[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ'-]{2,}(?:\s+[A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ'-]+)*"
)


def ocr_extract(
    front_text: np.ndarray,
    document_type: DocumentType,
    *,
    back_image: np.ndarray | None = None,
    mrz_bytes: bytes | None = None,
) -> OcrResult:
    """Extract identity fields from a document's text zone(s) and MRZ.

    Args:
        front_text: Cropped text zone of the document front
            (``NicZones.text_zone`` from :func:`crop_nic_zones`).
        document_type: Selects the field set and parsing rules.
        back_image: Preprocessed document back, required for NIC cards whose
            visual fields span both sides; ``None`` for single-page passports.
        mrz_bytes: RAW bytes of the image bearing the MRZ (the back for a NIC,
            the front for a passport). Read by PassportEye — must be the
            original image, not a preprocessed array.

    Returns:
        An :class:`OcrResult`; ``success`` is False when the mandatory
        fields could not be read with usable confidence.
    """
    if document_type is DocumentType.PASSPORT:
        return _extract_passport(front_text, mrz_bytes)
    return _extract_nic(front_text, back_image, mrz_bytes)


def _extract_nic(
    front_text: np.ndarray,
    back_image: np.ndarray | None,
    mrz_bytes: bytes | None,
) -> OcrResult:
    """Parse a Cameroonian NIC: visual fields + the (checksummed) MRZ.

    The MRZ (NIC v2, read from the raw back) is the trusted source for name,
    id, DOB, sex, and expiry; the visual OCR supplies place of birth and
    occupation, and is the only source for the older, MRZ-less NIC v1.
    """
    fields = _parse_fields(_ocr_text(front_text))
    if back_image is not None:
        fields = _prefer(fields, _parse_fields(_ocr_text(back_image)))
    if mrz_bytes is not None:
        fields = _prefer(fields, read_mrz_fields(mrz_bytes))
    return _build_result(fields)


def _extract_passport(
    page: np.ndarray, mrz_bytes: bytes | None
) -> OcrResult:
    """Parse a passport data page: visual fields plus the MRZ."""
    fields = _parse_fields(_ocr_text(page))
    if mrz_bytes is not None:
        fields = _prefer(fields, read_mrz_fields(mrz_bytes))
    return _build_result(fields)


def _ocr_text(image: np.ndarray, *, mrz: bool = False) -> str:
    """Run Tesseract over ``image`` and return the recognized text.

    The printed zones sit on a busy coloured guilloche background. Our own
    binarization (a local adaptive threshold) shredded that background into
    noise and wiped out the text; passing plain **grayscale** and letting
    Tesseract do its own binarization reads the fields cleanly. The image is
    still upscaled first — Tesseract wants tall glyphs. The MRZ is clean and
    monospaced, so it takes an Otsu pass with the OCR-B charset.
    """
    import cv2
    import pytesseract

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = _upscale_for_ocr(gray)
    if mrz:
        binary = cv2.threshold(
            gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
        )[1]
        whitelist = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"
        config = f"--psm 6 -c tessedit_char_whitelist={whitelist}"
        return pytesseract.image_to_string(binary, lang="eng", config=config)

    return pytesseract.image_to_string(
        gray, lang="fra+eng", config="--psm 6"
    )


def _upscale_for_ocr(
    gray: np.ndarray, *, target_height: int = 1000, max_scale: float = 3.0
) -> np.ndarray:
    """Enlarge a small crop so its text is tall enough for Tesseract."""
    import cv2

    height = gray.shape[0]
    if height >= target_height:
        return gray
    scale = min(max_scale, target_height / height)
    return cv2.resize(
        gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
    )


def _parse_fields(text: str) -> _Fields:
    """Extract labelled identity fields from raw OCR ``text``."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    fields: _Fields = {}

    surname = _value_after(lines, _SURNAME_LABEL, extract=_upper_value)
    given = _value_after(lines, _GIVEN_LABEL, extract=_upper_value)
    name = " ".join(part for part in (given, surname) if part)
    _set(fields, "full_name", name or None)
    _set(fields, "id_number", _value_after(lines, _ID_LABEL))
    _set(fields, "date_of_birth",
         _parse_date(_value_after(lines, _DOB_LABEL)))
    _set(fields, "expiry_date",
         _parse_date(_value_after(lines, _EXPIRY_LABEL)))
    _set(fields, "place_of_birth",
         _value_after(lines, _POB_LABEL, extract=_upper_value))
    _set(fields, "occupation",
         _value_after(lines, _OCCUPATION_LABEL, extract=_upper_value))
    _set(fields, "sex", _parse_sex(_value_after(lines, _SEX_LABEL)))
    return fields


def _clean_value(raw: str) -> str:
    """Trim OCR speckle around a value, keeping its meaningful core.

    Strips leading/trailing runs that carry no letter or digit (stray
    punctuation, guilloche marks) so ``'“ WILLIAMS ,'`` becomes
    ``'WILLIAMS'`` while inner spacing is preserved.
    """
    match = re.search(r"[^\W_].*[^\W_]|[^\W_]", raw)
    return match.group(0).strip() if match else ""


def _upper_value(raw: str) -> str | None:
    """Pull the printed ALL-CAPS value out of a candidate string.

    The card prints names, places, and occupations in uppercase, while the
    guilloche background OCRs as mixed-case speckle. Returning the first run
    of uppercase words (see :data:`_UPPER_VALUE_RE`) keeps ``'LIMBE'`` from
    ``'LIMBE noe Per'`` and rejects ``'joa id hn See'`` outright, so the
    caller falls through to the line that holds the real value.
    """
    match = _UPPER_VALUE_RE.search(raw)
    return match.group(0).strip() if match else None


def _value_after(
    lines: list[str],
    label: str,
    *,
    extract: Callable[[str], str | None] = _clean_value,
) -> str | None:
    """Return the value printed after ``label``, on its line or the next.

    The value may sit on the label's line or the row beneath it. ``extract``
    pulls the value out of a candidate string; a same-line remainder that
    yields nothing (a stray mark after the label, or mixed-case guilloche
    speckle) is skipped in favour of the next line, where the printed value
    usually sits. Alphabetic fields pass :func:`_upper_value` to reject that
    speckle; the rest use :func:`_clean_value`.
    """
    regex = re.compile(label, re.IGNORECASE)
    for index, line in enumerate(lines):
        match = regex.search(line)
        if match is None:
            continue
        tail = extract(line[match.end():])
        if tail:
            return tail
        if index + 1 < len(lines):
            return extract(lines[index + 1]) or None
    return None


def _parse_date(raw: str | None) -> date | None:
    """Parse a printed date into a :class:`date`, or ``None``."""
    if not raw:
        return None
    match = _DATE_RE.search(raw)
    if match is None:
        return None
    day, month, year = (int(group) for group in match.groups())
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_sex(raw: str | None) -> Sex | None:
    """Map a printed sex token to :class:`Sex`, or ``None``."""
    if not raw:
        return None
    for char in raw.upper():
        if char == "M":
            return Sex.M
        if char == "F":
            return Sex.F
    return None


def read_mrz_fields(image_bytes: bytes) -> _Fields:
    """Read the MRZ from RAW image bytes via PassportEye, ``{}`` if none.

    PassportEye does its own MRZ detection, rotation, and check-digit parsing,
    so it is handed the ORIGINAL image bytes — our preprocessing (deskew,
    threshold) destroys its accuracy. The read is trusted only above a minimum
    validity score; each date is used only when its own check digit passes.
    The printed CNI/NIC number lives in the MRZ optional data, preferred over
    the raw document number.
    """
    import io

    from passporteye import read_mrz

    mrz = read_mrz(io.BytesIO(image_bytes))
    if mrz is None:
        return {}
    data = mrz.to_dict()
    if int(data.get("valid_score", 0)) < _MIN_MRZ_SCORE:
        return {}

    fields: _Fields = {}
    name = " ".join(
        part.strip()
        for part in (data.get("names"), data.get("surname"))
        if part and part.strip()
    )
    _set(fields, "full_name", name or None, _MRZ_CONFIDENCE)

    cni = (data.get("optional1") or "").replace("<", "").strip()
    number = (data.get("number") or "").replace("<", "").strip()
    _set(fields, "id_number", cni or number or None, _MRZ_CONFIDENCE)

    if data.get("valid_date_of_birth"):
        _set(
            fields,
            "date_of_birth",
            _mrz_date(data.get("date_of_birth", ""), future=False),
            _MRZ_CONFIDENCE,
        )
    if data.get("valid_expiration_date"):
        _set(
            fields,
            "expiry_date",
            _mrz_date(data.get("expiration_date", ""), future=True),
            _MRZ_CONFIDENCE,
        )
    _set(fields, "sex", _parse_sex(data.get("sex")), _MRZ_CONFIDENCE)
    return fields


def _mrz_date(raw: str, *, future: bool) -> date | None:
    """Decode a 6-digit ``YYMMDD`` MRZ date, picking the century.

    Expiry dates are assumed to be 21st century; birth dates use a pivot on
    the current two-digit year so recent births are not read as a century
    in the future.
    """
    if len(raw) != 6 or not raw.isdigit():
        return None
    year, month, day = int(raw[:2]), int(raw[2:4]), int(raw[4:6])
    if future or year <= date.today().year % 100:
        century = 2000
    else:
        century = 1900
    try:
        return date(century + year, month, day)
    except ValueError:
        return None


def _set(
    fields: _Fields,
    key: str,
    value: Any,
    confidence: float = _VISUAL_CONFIDENCE,
) -> None:
    """Store ``value`` under ``key`` when it is truthy."""
    if value:
        fields[key] = (value, confidence)


def _prefer(base: _Fields, other: _Fields) -> _Fields:
    """Merge ``other`` into ``base``: fill gaps, override only if surer.

    Equal-confidence values keep ``base`` (so a card's front wins ties over
    its back); a strictly higher-confidence value — an MRZ field over the
    printed text — replaces it.
    """
    merged = dict(base)
    for key, (value, confidence) in other.items():
        if key not in merged or confidence > merged[key][1]:
            merged[key] = (value, confidence)
    return merged


def _build_result(fields: _Fields) -> OcrResult:
    """Assemble an :class:`OcrResult` from merged fields."""
    confidences = {key: round(conf, 2) for key, (_, conf) in fields.items()}
    success = all(key in fields for key in _REQUIRED_FIELDS)
    return OcrResult(
        success=success,
        full_name=_value(fields, "full_name"),
        id_number=_value(fields, "id_number"),
        date_of_birth=_value(fields, "date_of_birth"),
        place_of_birth=_value(fields, "place_of_birth"),
        expiry_date=_value(fields, "expiry_date"),
        sex=_value(fields, "sex"),
        occupation=_value(fields, "occupation"),
        field_confidences=confidences,
    )


def _value(fields: _Fields, key: str) -> Any:
    """Return the stored value for ``key``, or ``None``."""
    return fields[key][0] if key in fields else None
