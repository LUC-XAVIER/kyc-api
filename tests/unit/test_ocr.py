"""Unit tests for the OCR stage.

The Tesseract call (``_ocr_text``) is monkeypatched so these run without the
tesseract binary; they cover the parsing, MRZ decoding, and front/back merge
logic. Skipped when the optional ``ml`` extra (OpenCV/NumPy) is absent.
"""

import importlib.util
from datetime import date
from pathlib import Path

import pytest

from app.models.enums import DocumentType, Sex
from app.pipeline.stages import ocr

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("cv2") is None,
    reason="requires the optional `ml` extra (OpenCV)",
)

_MONO_FONT = Path("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf")


def _tesseract_ready() -> bool:
    """Whether the tesseract binary is installed and callable."""
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _blank() -> "object":
    """A small blank BGR array standing in for a cropped zone."""
    import numpy as np

    return np.zeros((10, 10, 3), dtype=np.uint8)


def _mrz_line(field_and_check: list[tuple[str, bool]], width: int) -> str:
    """Build one MRZ line, appending a valid check digit where asked."""
    out = ""
    for text, checked in field_and_check:
        out += text
        if checked:
            out += str(ocr._mrz_check_digit(text))
    return out.ljust(width, "<")


# --- date parsing --------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("12.03.1974", date(1974, 3, 12)),  # NIC dotted
        ("20 05 1982", date(1982, 5, 20)),  # passport spaced
        ("01/12/2030", date(2030, 12, 1)),  # slashed
        ("16.00.9999", None),               # invalid month/year
        ("no date here", None),
        (None, None),
    ],
)
def test_parse_date(raw: str | None, expected: date | None) -> None:
    """Dates parse across separators; invalid ones return None."""
    assert ocr._parse_date(raw) == expected


# --- MRZ check digits ----------------------------------------------------


def test_mrz_check_digit_matches_and_rejects() -> None:
    """A field validates against its own digit and rejects a wrong one."""
    field = "AB1234567"
    digit = str(ocr._mrz_check_digit(field))
    assert ocr._mrz_valid(field, digit)
    wrong = str((int(digit) + 1) % 10)
    assert not ocr._mrz_valid(field, wrong)


# --- MRZ decoding --------------------------------------------------------


def test_parse_td3_passport_mrz() -> None:
    """A valid two-line TD3 MRZ decodes name, number, DOB, sex, expiry."""
    line1 = "P<CMRCITIZEN<<JOHN".ljust(44, "<")
    line2 = _mrz_line(
        [
            ("AB1234567", True),   # passport number + check
            ("CMR", False),
            ("820520", True),      # DOB 1982-05-20 + check
            ("F", False),
            ("270515", True),      # expiry 2027-05-15 + check
        ],
        44,
    )

    fields = ocr._parse_mrz_lines([line1, line2])

    assert ocr._value(fields, "full_name") == "JOHN CITIZEN"
    assert ocr._value(fields, "id_number") == "AB1234567"
    assert ocr._value(fields, "date_of_birth") == date(1982, 5, 20)
    assert ocr._value(fields, "expiry_date") == date(2027, 5, 15)
    assert ocr._value(fields, "sex") is Sex.F


def test_parse_td1_nic_mrz() -> None:
    """A valid three-line TD1 MRZ decodes the NIC fields."""
    line1 = _mrz_line([("I<CMR", False), ("AA0000000", True)], 30)
    line2 = _mrz_line(
        [("751210", True), ("M", False), ("320112", True), ("CMR", False)],
        30,
    )
    line3 = "AHANDA<<DANIEL".ljust(30, "<")

    fields = ocr._parse_mrz_lines([line1, line2, line3])

    assert ocr._value(fields, "id_number") == "AA0000000"
    assert ocr._value(fields, "date_of_birth") == date(1975, 12, 10)
    assert ocr._value(fields, "expiry_date") == date(2032, 1, 12)
    assert ocr._value(fields, "full_name") == "DANIEL AHANDA"


def test_mrz_field_dropped_on_bad_check_digit() -> None:
    """A field whose check digit is wrong is not trusted."""
    line1 = "P<CMRCITIZEN<<JOHN".ljust(44, "<")
    # Number followed by a deliberately wrong check digit ("0").
    line2 = ("AB12345670" + "CMR" + "820520").ljust(44, "<")

    fields = ocr._parse_mrz_lines([line1, line2])

    assert "id_number" not in fields


# --- NIC front/back merge ------------------------------------------------


_NIC_V1_FRONT = """
NOMS/SURNAME WILLIAMS
PRENOMS/GIVEN NAMES JOHN CITIZEN
DATE DE NAISSANCE/DATE OF BIRTH 12.03.1974
LIEU DE NAISSANCE/PLACE OF BIRTH NYLIM-KOT
SEXE/SEX M
PROFESSION/OCCUPATION SANS PROFESSION
"""

_NIC_V1_BACK = """
DATE D'EXPIRATION/DATE OF EXPIRY 16.05.2030
NUMERO D'IDENTIFICATION/IDENTIFICATION NUMBER 1010
"""


def test_nic_merges_expiry_and_id_from_back(monkeypatch) -> None:
    """NIC v1: front lacks expiry/id; they come from the back."""
    texts = iter([_NIC_V1_FRONT, _NIC_V1_BACK])
    monkeypatch.setattr(ocr, "_ocr_text", lambda img, **kw: next(texts))
    monkeypatch.setattr(ocr, "_parse_mrz", lambda img: {})

    result = ocr.ocr_extract(_blank(), DocumentType.NIC, back_image=_blank())

    assert result.success
    assert result.full_name == "JOHN CITIZEN WILLIAMS"
    assert result.date_of_birth == date(1974, 3, 12)
    assert result.place_of_birth == "NYLIM-KOT"
    assert result.expiry_date == date(2030, 5, 16)
    assert result.id_number == "1010"
    assert result.occupation == "SANS PROFESSION"


def test_nic_without_back_is_incomplete(monkeypatch) -> None:
    """Front alone can't satisfy the required fields for a NIC v1."""
    monkeypatch.setattr(ocr, "_ocr_text", lambda img, **kw: _NIC_V1_FRONT)
    monkeypatch.setattr(ocr, "_parse_mrz", lambda img: {})

    result = ocr.ocr_extract(_blank(), DocumentType.NIC)

    assert not result.success
    assert result.expiry_date is None


def test_mrz_overrides_visual_field(monkeypatch) -> None:
    """A check-valid MRZ value outranks the printed text for that field."""
    front = "NOM/SURNAME MISREAD\nDATE OF EXPIRY 01.01.2030\nNIC NUMBER X1"
    monkeypatch.setattr(ocr, "_ocr_text", lambda img, **kw: front)
    monkeypatch.setattr(
        ocr,
        "_parse_mrz",
        lambda img: {"full_name": ("JOHN CITIZEN", ocr._MRZ_CONFIDENCE)},
    )

    result = ocr.ocr_extract(_blank(), DocumentType.NIC, back_image=_blank())

    assert result.full_name == "JOHN CITIZEN"
    assert result.field_confidences["full_name"] == 0.98


# --- dispatch ------------------------------------------------------------


def test_dispatch_routes_by_document_type(monkeypatch) -> None:
    """ocr_extract routes NIC vs passport to the right parser."""
    monkeypatch.setattr(ocr, "_extract_nic", lambda f, b: "nic")
    monkeypatch.setattr(ocr, "_extract_passport", lambda p: "passport")

    assert ocr.ocr_extract(_blank(), DocumentType.NIC) == "nic"
    assert ocr.ocr_extract(_blank(), DocumentType.PASSPORT) == "passport"


# --- real OCR round-trip (synthetic valid MRZ) ---------------------------
# These run the actual tesseract engine on a rendered card, so they need the
# binary and a monospaced font; skipped cleanly when either is absent.


def _render_mrz_card() -> "tuple[object, dict]":
    """Render a card bearing a valid TD3 MRZ; return the image and truth."""
    import cv2
    import numpy as np
    from PIL import Image, ImageDraw, ImageFont

    def check(field: str) -> str:
        return str(ocr._mrz_check_digit(field))

    number, dob, expiry = "AB1234567", "820520", "270515"
    line1 = "P<CMRCITIZEN<<JOHN".ljust(44, "<")
    line2 = (
        number + check(number) + "CMR" + dob + check(dob)
        + "F" + expiry + check(expiry)
    ).ljust(44, "<")

    image = Image.new("RGB", (900, 560), "white")
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype(str(_MONO_FONT), 34)
    draw.text((30, 40), "NOM/SURNAME CITIZEN", fill="black", font=font)
    draw.text((30, 460), line1, fill="black", font=font)
    draw.text((30, 505), line2, fill="black", font=font)

    truth = {
        "full_name": "JOHN CITIZEN",
        "id_number": number,
        "date_of_birth": date(1982, 5, 20),
        "expiry_date": date(2027, 5, 15),
        "sex": Sex.F,
    }
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR), truth


@pytest.mark.skipif(
    not _MONO_FONT.exists() or not _tesseract_ready(),
    reason="requires the tesseract binary and a monospaced TTF font",
)
def test_mrz_first_locates_and_decodes_rendered_card() -> None:
    """Locate + OCR + decode a valid MRZ from a full synthetic card.

    Asserts the guarantees that hold deterministically: the band is found,
    every decoded field is correct (the check digits forbid garbage), and a
    healthy majority of fields survive. Per-character OCR is not perfect —
    that is precisely why the check digits gate each field.
    """
    card, truth = _render_mrz_card()

    band = ocr._locate_mrz(card)
    assert band is not None
    assert band.shape[1] > card.shape[1] * 0.6  # spans most of the width

    fields = ocr._parse_mrz(card)
    for key, (value, _) in fields.items():
        assert value == truth[key]  # never a wrong value
    assert len(fields) >= 3  # the check-valid majority decodes
