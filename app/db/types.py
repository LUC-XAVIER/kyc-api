"""Column types that encrypt personal data on the way to the database.

These keep encryption out of the query and route layers: a model declares
``EncryptedString`` instead of ``String`` and every read and write is sealed
transparently. See :mod:`app.core.crypto` for the wire format and why the
face embedding is deliberately *not* encrypted this way.

Values are stored as ``BYTEA``. Nothing filters on these columns, which is
what makes randomized (non-deterministic) encryption affordable — a
``WHERE full_name = ...`` would silently match nothing.
"""

from datetime import date

from sqlalchemy import LargeBinary
from sqlalchemy.types import TypeDecorator

from app.core.crypto import decrypt, encrypt


class EncryptedString(TypeDecorator):
    """A text column sealed with AES-GCM at rest."""

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(
        self, value: str | None, dialect: object
    ) -> bytes | None:
        """Seal a Python string on the way to the database."""
        if value is None:
            return None
        return encrypt(value.encode())

    def process_result_value(
        self, value: bytes | None, dialect: object
    ) -> str | None:
        """Open a stored value on the way back out."""
        if value is None:
            return None
        return decrypt(bytes(value)).decode()


class EncryptedDate(TypeDecorator):
    """A date column sealed with AES-GCM at rest.

    Stored as an ISO-8601 string inside the ciphertext, so the value keeps
    its meaning independently of the database's date representation.
    """

    impl = LargeBinary
    cache_ok = True

    def process_bind_param(
        self, value: date | None, dialect: object
    ) -> bytes | None:
        """Seal a date on the way to the database."""
        if value is None:
            return None
        return encrypt(value.isoformat().encode())

    def process_result_value(
        self, value: bytes | None, dialect: object
    ) -> date | None:
        """Open a stored date on the way back out."""
        if value is None:
            return None
        return date.fromisoformat(decrypt(bytes(value)).decode())
