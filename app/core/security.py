"""API-key generation, hashing, and verification primitives.

Pure functions only — no database, no FastAPI. An API key is shown to the
MFI exactly once at creation time; only its prefix (for lookup/display) and
an HMAC-SHA256 digest of the secret (for verification) are persisted, per
NFR03. The server-side pepper (``settings.api_key_pepper``) is mixed into
the digest so a database leak alone does not reveal usable keys.

"""

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

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


# --- Single-use email tokens (signup invites, PIN resets) ---------------
# The raw token travels in the emailed link; only its SHA-256 digest is
# stored, so a database leak can't be turned back into a usable link.


def generate_token() -> str:
    """Return a new URL-safe single-use token (the raw value to email)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Return the stored SHA-256 digest of an email token."""
    return hashlib.sha256(token.encode()).hexdigest()


# --- Dashboard staff passwords (bcrypt) ---------------------------------
# bcrypt only consumes the first 72 bytes of its input, so a long password
# would be silently truncated (or rejected outright by bcrypt >= 4.1). We
# SHA-256 pre-hash to a fixed 44-byte token first, so every password is
# hashed in full and uniformly, regardless of length.


def _prepare_password(password: str) -> bytes:
    """Return a fixed-length, bcrypt-safe token for ``password``."""
    digest = hashlib.sha256(password.encode()).digest()
    return base64.b64encode(digest)


def hash_password(password: str) -> str:
    """Return a salted bcrypt hash of ``password`` for storage.

    Args:
        password: The plaintext password chosen by the staff member.

    Returns:
        The bcrypt hash string, safe to persist in ``agents.hashed_pin``.
    """
    hashed = bcrypt.hashpw(_prepare_password(password), bcrypt.gensalt())
    return hashed.decode()


def verify_password(password: str, hashed: str) -> bool:
    """Constant-time check that ``password`` matches a stored bcrypt hash.

    Args:
        password: The candidate password presented at login.
        hashed: The bcrypt hash previously stored for the account.

    Returns:
        ``True`` iff the password is authentic. A malformed stored hash
        yields ``False`` rather than raising.
    """
    try:
        return bcrypt.checkpw(_prepare_password(password), hashed.encode())
    except ValueError:
        return False


# --- Dashboard session tokens (JWT) -------------------------------------


def create_access_token(
    *, subject: str, role: str, expires_delta: timedelta | None = None
) -> str:
    """Mint a signed JWT for an authenticated dashboard session.

    Args:
        subject: The account identifier to place in the ``sub`` claim
            (the agent's UUID as a string).
        role: The account's :class:`~app.models.enums.AgentRole` value,
            carried in a ``role`` claim so the UI/RBAC can branch on it.
        expires_delta: Optional lifetime override; defaults to
            ``settings.access_token_expire_minutes``.

    Returns:
        The encoded, signed JWT string.
    """
    now = datetime.now(UTC)
    expire = now + (
        expires_delta
        or timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload = {"sub": subject, "role": role, "iat": now, "exp": expire}
    return jwt.encode(
        payload, settings.secret_key, algorithm=settings.jwt_algorithm
    )


def decode_access_token(token: str) -> dict:
    """Decode and validate a dashboard session JWT.

    Args:
        token: The encoded JWT presented on a request.

    Returns:
        The decoded claims (``sub``, ``role``, ``iat``, ``exp``).

    Raises:
        jwt.InvalidTokenError: If the token is malformed, tampered, or
            expired (callers translate this into a 401).
    """
    return jwt.decode(
        token, settings.secret_key, algorithms=[settings.jwt_algorithm]
    )
