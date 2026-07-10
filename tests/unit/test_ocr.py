"""Unit tests for the OCR stage.

The Tesseract call (``_ocr_text``) and the PassportEye MRZ reader are
monkeypatched so these run without the tesseract binary or a real MRZ image;
they cover date parsing, the PassportEye field mapping, and the front/back/
MRZ merge. Skipped when the optional ``ml`` extra (OpenCV/NumPy) is absent.
"""

import importlib.util
from datetime import date

import pytest

from app.models.enums import DocumentType, Sex
from app.pipeline.stages import ocr

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("cv2") is None,
    reason="requires the optional `ml` extra (OpenCV)",
)


def _blank() -> "object":
    """A small blank BGR array standing in for a cropped zone."""
    import numpy as np

    return np.zeros((10, 10, 3), dtype=np.uint8)


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


# --- MRZ via PassportEye (mocked) ----------------------------------------


class _FakeMrz:
    def __init__(self, data: dict) -> None:
        self._data = data

    def to_dict(self) -> dict:
        return self._data


def _valid_mrz_data() -> dict:
    return {
        "valid_score": 100,
        "surname": "FONING LACKMATA",
        "names": "LUC XAVIER",
        "number": "100701252",
        "optional1": "AA14700081<<<<<",
        "date_of_birth": "050522",
        "expiration_date": "350901",
        "sex": "M",
        "valid_date_of_birth": True,
        "valid_expiration_date": True,
    }


def test_read_mrz_fields_maps_passporteye(monkeypatch) -> None:
    """Fields map correctly; the CNI number comes from the optional data."""
    import passporteye

    monkeypatch.setattr(
        passporteye, "read_mrz", lambda src: _FakeMrz(_valid_mrz_data())
    )

    fields = ocr.read_mrz_fields(b"raw-image-bytes")

    assert ocr._value(fields, "full_name") == "LUC XAVIER FONING LACKMATA"
    assert ocr._value(fields, "id_number") == "AA14700081"  # optional1
    assert ocr._value(fields, "date_of_birth") == date(2005, 5, 22)
    assert ocr._value(fields, "expiry_date") == date(2035, 9, 1)
    assert ocr._value(fields, "sex") is Sex.M


def test_read_mrz_fields_low_score_is_ignored(monkeypatch) -> None:
    """An MRZ read below the validity floor is discarded."""
    import passporteye

    data = _valid_mrz_data() | {"valid_score": 10}
    monkeypatch.setattr(passporteye, "read_mrz", lambda src: _FakeMrz(data))

    assert ocr.read_mrz_fields(b"x") == {}


def test_read_mrz_fields_none_when_no_mrz(monkeypatch) -> None:
    """No MRZ found yields no fields."""
    import passporteye

    monkeypatch.setattr(passporteye, "read_mrz", lambda src: None)

    assert ocr.read_mrz_fields(b"x") == {}


def test_read_mrz_fields_skips_dates_failing_check(monkeypatch) -> None:
    """A date whose check digit failed is not trusted."""
    import passporteye

    data = _valid_mrz_data() | {"valid_expiration_date": False}
    monkeypatch.setattr(passporteye, "read_mrz", lambda src: _FakeMrz(data))

    fields = ocr.read_mrz_fields(b"x")
    assert "expiry_date" not in fields
    assert ocr._value(fields, "date_of_birth") == date(2005, 5, 22)


# --- NIC v1 (no MRZ): visual front/back merge ----------------------------


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


def test_nic_v1_merges_visual_front_and_back(monkeypatch) -> None:
    """NIC v1 has no MRZ; expiry/id come from the back's visual text."""
    texts = iter([_NIC_V1_FRONT, _NIC_V1_BACK])
    monkeypatch.setattr(ocr, "_ocr_text", lambda img, **kw: next(texts))

    result = ocr.ocr_extract(_blank(), DocumentType.NIC, back_image=_blank())

    assert result.success
    assert result.full_name == "JOHN CITIZEN WILLIAMS"
    assert result.date_of_birth == date(1974, 3, 12)
    assert result.place_of_birth == "NYLIM-KOT"
    assert result.expiry_date == date(2030, 5, 16)
    assert result.id_number == "1010"


def test_nic_without_back_is_incomplete(monkeypatch) -> None:
    """Front alone can't satisfy the required fields for a NIC v1."""
    monkeypatch.setattr(ocr, "_ocr_text", lambda img, **kw: _NIC_V1_FRONT)

    result = ocr.ocr_extract(_blank(), DocumentType.NIC)

    assert not result.success
    assert result.expiry_date is None


# --- uppercase value extraction (guilloche speckle rejection) -------------


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("LIMBE noe Per", "LIMBE"),          # value + trailing speckle
        ("ETUDIANT ae tee Lee", "ETUDIANT"),
        ("SANS PROFESSION", "SANS PROFESSION"),  # multi-word value
        ("NYLIM-KOT", "NYLIM-KOT"),          # hyphenated
        (" | joa id hn See", None),          # pure mixed-case speckle
        ("NA = ee ae", None),                # 2-letter run is too short
        ("", None),
    ],
)
def test_upper_value(raw: str, expected: str | None) -> None:
    """Only an ALL-CAPS run (>=3 chars) counts as a printed value."""
    assert ocr._upper_value(raw) == expected


# The real NIC back: the value sits on the line *below* each label, while
# the label line trails into guilloche speckle. The parser must skip the
# speckle and reach LIMBE / ETUDIANT.
_REAL_NIC_BACK = """
LIEU DE NAISSANGE/PLACE OF BIRTH | joa id hn See
+) LIMBE noe Per
PROFESSION / OCCUPATION NA = ee ae
ee ETUDIANT ae tee Lee
"""


def test_parse_fields_skips_speckle_for_next_line_value() -> None:
    """place_of_birth / occupation come from the value line, not the noise."""
    fields = ocr._parse_fields(_REAL_NIC_BACK)

    assert ocr._value(fields, "place_of_birth") == "LIMBE"
    assert ocr._value(fields, "occupation") == "ETUDIANT"


def test_mrz_overrides_visual_field(monkeypatch) -> None:
    """A trusted MRZ value outranks the printed text for that field."""
    front = "NOM/SURNAME MISREAD\nDATE OF EXPIRY 01.01.2030"
    monkeypatch.setattr(ocr, "_ocr_text", lambda img, **kw: front)
    monkeypatch.setattr(
        ocr,
        "read_mrz_fields",
        lambda b: {"full_name": ("JOHN CITIZEN", ocr._MRZ_CONFIDENCE)},
    )

    result = ocr.ocr_extract(
        _blank(), DocumentType.NIC, back_image=_blank(), mrz_bytes=b"raw"
    )

    assert result.full_name == "JOHN CITIZEN"
    assert result.field_confidences["full_name"] == 0.98


# --- dispatch ------------------------------------------------------------


def test_dispatch_routes_by_document_type(monkeypatch) -> None:
    """ocr_extract routes NIC vs passport to the right parser."""
    monkeypatch.setattr(ocr, "_extract_nic", lambda f, b, m: "nic")
    monkeypatch.setattr(ocr, "_extract_passport", lambda p, m: "passport")

    assert ocr.ocr_extract(_blank(), DocumentType.NIC) == "nic"
    assert ocr.ocr_extract(_blank(), DocumentType.PASSPORT) == "passport"
