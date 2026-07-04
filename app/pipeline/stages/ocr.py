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
    import numpy as np

# Confidence assigned by source. An MRZ field is trusted more than the same
# value read from the printed text because its check digit is validated.
_VISUAL_CONFIDENCE = 0.75
_MRZ_CONFIDENCE = 0.98

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

# MRZ check-digit weights, cycled over the field characters (ICAO 9303).
_MRZ_WEIGHTS = (7, 3, 1)


def ocr_extract(
    front_text: np.ndarray,
    document_type: DocumentType,
    *,
    back_image: np.ndarray | None = None,
) -> OcrResult:
    """Extract identity fields from a document's text zone(s).

    Args:
        front_text: Cropped text zone of the document front
            (``NicZones.text_zone`` from :func:`crop_nic_zones`).
        document_type: Selects the field set and parsing rules.
        back_image: Preprocessed document back, required for NIC cards whose
            fields span both sides; ``None`` for single-page passports.

    Returns:
        An :class:`OcrResult`; ``success`` is False when the mandatory
        fields could not be read with usable confidence.
    """
    if document_type is DocumentType.PASSPORT:
        return _extract_passport(front_text)
    return _extract_nic(front_text, back_image)


def _extract_nic(
    front_text: np.ndarray, back_image: np.ndarray | None
) -> OcrResult:
    """Parse a Cameroonian NIC, merging front- and back-side fields."""
    fields = _parse_fields(_ocr_text(front_text))
    if back_image is not None:
        fields = _prefer(fields, _parse_fields(_ocr_text(back_image)))
        fields = _prefer(fields, _parse_mrz(back_image))
    return _build_result(fields)


def _extract_passport(page: np.ndarray) -> OcrResult:
    """Parse a passport data page: visual fields plus the bottom MRZ."""
    fields = _parse_fields(_ocr_text(page))
    fields = _prefer(fields, _parse_mrz(page))
    return _build_result(fields)


def _ocr_text(image: np.ndarray, *, mrz: bool = False) -> str:
    """Run Tesseract over ``image`` and return the recognized text.

    The printed zones sit on a low-contrast guilloche background, so a
    global (Otsu) threshold wipes out the text. Instead the text is
    upscaled — Tesseract wants tall glyphs — then denoised and binarized
    with a local adaptive threshold that ignores the background wash. The
    MRZ is clean and monospaced, so it takes an Otsu pass with the OCR-B
    charset and single-block segmentation.
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

    gray = cv2.fastNlMeansDenoising(gray, h=10)
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 15
    )
    return pytesseract.image_to_string(
        binary, lang="fra+eng", config="--psm 6"
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

    surname = _value_after(lines, _SURNAME_LABEL)
    given = _value_after(lines, _GIVEN_LABEL)
    name = " ".join(part for part in (given, surname) if part)
    _set(fields, "full_name", name or None)
    _set(fields, "id_number", _value_after(lines, _ID_LABEL))
    _set(fields, "date_of_birth",
         _parse_date(_value_after(lines, _DOB_LABEL)))
    _set(fields, "expiry_date",
         _parse_date(_value_after(lines, _EXPIRY_LABEL)))
    _set(fields, "place_of_birth", _value_after(lines, _POB_LABEL))
    _set(fields, "occupation", _value_after(lines, _OCCUPATION_LABEL))
    _set(fields, "sex", _parse_sex(_value_after(lines, _SEX_LABEL)))
    return fields


def _value_after(lines: list[str], label: str) -> str | None:
    """Return the value printed after ``label``, on its line or the next.

    The value may sit on the label's line or the row beneath it. Each
    candidate is cleaned of surrounding OCR speckle; a same-line remainder
    that cleans away to nothing (a stray mark after the label) is skipped
    in favour of the next line, where the printed value usually sits.
    """
    regex = re.compile(label, re.IGNORECASE)
    for index, line in enumerate(lines):
        match = regex.search(line)
        if match is None:
            continue
        tail = _clean_value(line[match.end():])
        if tail:
            return tail
        if index + 1 < len(lines):
            return _clean_value(lines[index + 1]) or None
    return None


def _clean_value(raw: str) -> str:
    """Trim OCR speckle around a value, keeping its meaningful core.

    Strips leading/trailing runs that carry no letter or digit (stray
    punctuation, guilloche marks) so ``'“ WILLIAMS ,'`` becomes
    ``'WILLIAMS'`` while inner spacing is preserved.
    """
    match = re.search(r"[^\W_].*[^\W_]|[^\W_]", raw)
    return match.group(0).strip() if match else ""


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


def _parse_mrz(image: np.ndarray) -> _Fields:
    """Locate, OCR, and decode the MRZ band, ``{}`` if none is found."""
    band = _locate_mrz(image)
    target = band if band is not None else image
    return _parse_mrz_lines(_ocr_text(target, mrz=True).splitlines())


def _locate_mrz(image: np.ndarray) -> np.ndarray | None:
    """Return a crop of the MRZ band, or ``None`` if none stands out.

    The MRZ is a wide block of dense monospaced text. A blackhat + gradient
    pass highlights the strokes, morphological closing fuses the glyphs into
    one bar, and the widest near-full-width, high-aspect-ratio component is
    taken as the band. Isolating it keeps the guilloche background out of
    the character-level OCR.
    """
    import cv2

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    height, width = gray.shape
    line_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(13, width // 25), 5)
    )
    blackhat = cv2.morphologyEx(gray, cv2.MORPH_BLACKHAT, line_kernel)
    gradient = cv2.convertScaleAbs(
        cv2.Sobel(blackhat, cv2.CV_32F, 1, 0, ksize=-1)
    )
    gradient = cv2.normalize(
        gradient, None, 0, 255, cv2.NORM_MINMAX
    ).astype("uint8")
    gradient = cv2.morphologyEx(gradient, cv2.MORPH_CLOSE, line_kernel)
    band_mask = cv2.threshold(
        gradient, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )[1]
    block_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (max(21, width // 18), max(11, height // 25))
    )
    band_mask = cv2.morphologyEx(band_mask, cv2.MORPH_CLOSE, block_kernel)
    band_mask = cv2.erode(band_mask, None, iterations=2)

    contours, _ = cv2.findContours(
        band_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )
    best: tuple[int, int, int, int] | None = None
    for contour in contours:
        x, y, box_w, box_h = cv2.boundingRect(contour)
        if box_w / box_h <= 4 or box_w / width <= 0.6:
            continue
        if best is None or box_w * box_h > best[2] * best[3]:
            best = (x, y, box_w, box_h)
    if best is None:
        return None

    x, y, box_w, box_h = best
    pad = int(0.02 * height)
    top, bottom = max(0, y - pad), min(height, y + box_h + pad)
    return image[top:bottom, x:min(width, x + box_w)]


def _parse_mrz_lines(lines: list[str]) -> _Fields:
    """Decode MRZ text lines, dispatching on TD1 (NIC) vs TD3 (passport).

    Format is decided by line count — three lines for a TD1 ID card, two
    for a TD3 passport — rather than exact length, since OCR routinely
    trims or pads the trailing ``<`` fillers. Each line is normalized to
    its canonical width so the fixed field offsets line up.
    """
    mrz = [
        line.replace(" ", "").upper()
        for line in lines
        if line.count("<") >= 3 and len(line.strip()) >= 20
    ]
    if len(mrz) >= 3:
        return _parse_td1([_fit(line, 30) for line in mrz[:3]])
    if len(mrz) == 2:
        return _parse_td3([_fit(line, 44) for line in mrz[:2]])
    return {}


def _fit(line: str, width: int) -> str:
    """Normalize an MRZ line to ``width`` (truncate long, pad with '<')."""
    return line[:width].ljust(width, "<")


def _parse_td3(lines: list[str]) -> _Fields:
    """Decode a two-line TD3 (passport) MRZ."""
    line1, line2 = lines
    fields: _Fields = {}
    _set_mrz_name(fields, line1[5:])
    _set_mrz(fields, "id_number", line2[0:9], line2[9],
             line2[0:9].replace("<", ""))
    _set_mrz(fields, "date_of_birth", line2[13:19], line2[19],
             _mrz_date(line2[13:19], future=False))
    _set(fields, "sex", _parse_sex(line2[20]), _MRZ_CONFIDENCE)
    _set_mrz(fields, "expiry_date", line2[21:27], line2[27],
             _mrz_date(line2[21:27], future=True))
    return fields


def _parse_td1(lines: list[str]) -> _Fields:
    """Decode a three-line TD1 (NIC) MRZ."""
    line1, line2, line3 = lines
    fields: _Fields = {}
    _set_mrz(fields, "id_number", line1[5:14], line1[14],
             line1[5:14].replace("<", ""))
    _set_mrz(fields, "date_of_birth", line2[0:6], line2[6],
             _mrz_date(line2[0:6], future=False))
    _set(fields, "sex", _parse_sex(line2[7]), _MRZ_CONFIDENCE)
    _set_mrz(fields, "expiry_date", line2[8:14], line2[14],
             _mrz_date(line2[8:14], future=True))
    _set_mrz_name(fields, line3)
    return fields


def _set_mrz_name(fields: _Fields, block: str) -> None:
    """Split an MRZ ``SURNAME<<GIVEN`` block and store ``full_name``."""
    surname, _, given = block.partition("<<")
    surname = surname.replace("<", " ").strip()
    given = given.replace("<", " ").strip()
    name = " ".join(part for part in (given, surname) if part)
    _set(fields, "full_name", name or None, _MRZ_CONFIDENCE)


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


def _mrz_check_digit(field: str) -> int:
    """Compute the ICAO 9303 check digit over ``field``."""
    total = 0
    for position, char in enumerate(field):
        if char.isdigit():
            value = int(char)
        elif char.isalpha():
            value = ord(char) - 55  # 'A' -> 10 … 'Z' -> 35
        else:
            value = 0  # filler '<'
        total += value * _MRZ_WEIGHTS[position % 3]
    return total % 10


def _mrz_valid(field: str, check: str) -> bool:
    """Return whether ``check`` is the valid check digit for ``field``."""
    return check.isdigit() and _mrz_check_digit(field) == int(check)


def _set_mrz(
    fields: _Fields, key: str, raw_field: str, check: str, value: Any
) -> None:
    """Store an MRZ ``value`` only when the field's check digit validates.

    ``raw_field`` is the fixed-width MRZ substring the check digit covers
    (fillers included); ``value`` is the cleaned/parsed value to store.
    """
    if value and _mrz_valid(raw_field, check):
        _set(fields, key, value, _MRZ_CONFIDENCE)


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
