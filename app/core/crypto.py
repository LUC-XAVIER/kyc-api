"""Authenticated encryption for personal data stored at rest (NFR03/NFR04).

The extracted identity fields (name, NIC number, date and place of birth)
are the directly identifying output of the pipeline, so they are encrypted
in the column rather than left readable to anything holding a database dump
or a stale backup. Face embeddings are covered by volume encryption instead:
they stay in a pgvector column so similarity search can move into Postgres
as tenants grow (see ``docs/DASHBOARD-BACKEND.md`` §10).

AES-256-GCM is used in its authenticated mode, so tampering with a stored
value is detected on read rather than silently returning wrong data. The
nonce is random per write, which means encryption is *not* deterministic:
the same name yields a different ciphertext every time. That defeats
equality search on these columns by design — nothing queries them, and
deterministic encryption would leak which rows share a value.
"""

import base64
import os
from functools import lru_cache

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

# Wire format: VERSION || NONCE || CIPHERTEXT+TAG. The leading byte lets a
# future key rotation re-encrypt lazily by recognising which key sealed a
# value, without a flag day.
_VERSION = b"\x01"
_NONCE_BYTES = 12  # 96 bits, the size AES-GCM is specified for.
_KEY_BYTES = 32  # AES-256.


class DecryptionError(RuntimeError):
    """A stored value could not be decrypted or failed authentication."""


@lru_cache
def _cipher() -> AESGCM:
    """Return the AES-GCM cipher for the configured key.

    Cached: key decoding is pure, and this runs on every row read.

    Raises:
        ValueError: If the configured key is missing or not a base64
            encoding of exactly 32 bytes.
    """
    raw = settings.encryption_key
    if not raw:
        raise ValueError(
            "ENCRYPTION_KEY is not set; personal data cannot be stored."
        )
    try:
        key = base64.urlsafe_b64decode(raw)
    except (ValueError, TypeError) as exc:
        raise ValueError("ENCRYPTION_KEY must be base64-encoded.") from exc
    if len(key) != _KEY_BYTES:
        raise ValueError(
            f"ENCRYPTION_KEY must decode to {_KEY_BYTES} bytes, "
            f"got {len(key)}."
        )
    return AESGCM(key)


def encrypt(plaintext: bytes) -> bytes:
    """Seal ``plaintext`` for storage.

    Args:
        plaintext: The raw bytes to protect.

    Returns:
        The versioned envelope: version byte, nonce, then ciphertext+tag.
    """
    nonce = os.urandom(_NONCE_BYTES)
    sealed = _cipher().encrypt(nonce, plaintext, None)
    return _VERSION + nonce + sealed


def decrypt(blob: bytes) -> bytes:
    """Open a value produced by :func:`encrypt`.

    Args:
        blob: The stored envelope.

    Returns:
        The original plaintext bytes.

    Raises:
        DecryptionError: If the envelope is malformed, was sealed with a
            different key, or has been tampered with.
    """
    if not blob or blob[:1] != _VERSION:
        raise DecryptionError("Unrecognised ciphertext envelope.")
    nonce = blob[1 : 1 + _NONCE_BYTES]
    sealed = blob[1 + _NONCE_BYTES :]
    try:
        return _cipher().decrypt(nonce, sealed, None)
    except InvalidTag as exc:
        raise DecryptionError(
            "Stored value failed authentication (wrong key or tampered)."
        ) from exc


def generate_key() -> str:
    """Return a fresh base64 key suitable for ``ENCRYPTION_KEY``.

    Intended for operators bootstrapping a deployment::

        python -c "from app.core.crypto import generate_key; \
print(generate_key())"
    """
    return base64.urlsafe_b64encode(os.urandom(_KEY_BYTES)).decode()
