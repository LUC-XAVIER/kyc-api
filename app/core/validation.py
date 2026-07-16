"""Reusable input validation (shared across schemas)."""

import re

_DIGITS = re.compile(r"\D")


def normalize_cm_phone(raw: str) -> str:
    """Normalize a Cameroonian phone number to ``+237`` + 9 digits.

    Accepts local (``6 99 00 11 22``), country-coded (``237...``), or fully
    qualified (``+237...``) input, ignoring spaces/dashes.

    Raises:
        ValueError: If it isn't 9 national digits.
    """
    digits = _DIGITS.sub("", raw)
    if digits.startswith("237"):
        digits = digits[3:]
    if len(digits) != 9:
        raise ValueError(
            "Enter a valid Cameroonian phone number (+237 and 9 digits)."
        )
    return "+237" + digits


def try_normalize_cm_phone(raw: str) -> str | None:
    """Return the normalized phone, or ``None`` if it isn't a valid one."""
    try:
        return normalize_cm_phone(raw)
    except ValueError:
        return None
