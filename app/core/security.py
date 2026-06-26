"""API-key generation, hashing, and verification primitives.

Pure functions only — no database, no FastAPI. An API key is shown to the
MFI exactly once at creation time; only its prefix (for lookup/display) and
an HMAC-SHA256 digest of the secret (for verification) are persisted, per
NFR03. The server-side pepper (``settings.api_key_pepper``) is mixed into
the digest so a database leak alone does not reveal usable keys.

"""

import hashlib
import hmac
import secrets
from dataclasses import dataclass

from app.core.config import settings

KEY_PREFIX = "kyc_live_"
# Bytes of randomness in the secret part (token_urlsafe length, not chars).
SECRET_NBYTES = 32
# Chars of the full key kept as the stored, human-visible prefix.
PREFIX_DISPLAY_LEN = 16


@dataclass(frozen=True)
class GeneratedKey:
    """A freshly minted API key, returned to the caller exactly once.

    Attributes:
        full_key: The complete key string handed to the MFI (never stored).
        prefix: The leading, non-secret slice persisted for lookup/display.
        hashed_key: The HMAC-SHA256 digest persisted for verification.
    """

    full_key: str
    prefix: str
    hashed_key: str


def generate_api_key() -> GeneratedKey:
    """Mint a new API key with prefix and stored hash.

    Returns:
        A :class:`GeneratedKey`. Persist ``prefix`` and ``hashed_key``;
        surface ``full_key`` to the MFI once and then discard it.
    """
    full_key = KEY_PREFIX + secrets.token_urlsafe(SECRET_NBYTES)
    prefix = full_key[:PREFIX_DISPLAY_LEN]
    hashed_key = hash_api_key(full_key)

    return GeneratedKey(
        full_key=full_key, prefix=prefix, hashed_key=hashed_key
    )


def hash_api_key(full_key: str) -> str:
    """Return the HMAC-SHA256 hex digest of ``full_key`` under the pepper.

    Args:
        full_key: The complete API-key string.

    Returns:
        Hex-encoded digest suitable for storage in ``api_keys.hashed_key``.
    """
    return hmac.new(
        settings.api_key_pepper.encode(), full_key.encode(), hashlib.sha256
    ).hexdigest()


def verify_api_key(full_key: str, stored_hash: str) -> bool:
    """Constant-time check that ``full_key`` matches ``stored_hash``.

    Args:
        full_key: The candidate key presented on a request.
        stored_hash: The digest previously persisted for that key.

    Returns:
        ``True`` iff the key is authentic.
    """
    return hmac.compare_digest(hash_api_key(full_key), stored_hash)


def extract_prefix(full_key: str) -> str:
    """Return the stored/display prefix slice of a full key."""
    return full_key[:PREFIX_DISPLAY_LEN]
