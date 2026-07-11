"""Unit tests for the API-key security primitives (no DB)."""

from datetime import timedelta

import jwt
import pytest

from app.core.security import (
    KEY_PREFIX,
    PREFIX_DISPLAY_LEN,
    create_access_token,
    decode_access_token,
    extract_prefix,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_api_key,
    verify_password,
)


def test_generated_key_carries_brand_prefix() -> None:
    """Every minted key starts with the fixed brand prefix."""
    key = generate_api_key()
    assert key.full_key.startswith(KEY_PREFIX)


def test_prefix_is_the_display_slice() -> None:
    """The stored prefix is the leading display slice of the full key."""
    key = generate_api_key()
    assert key.prefix == key.full_key[:PREFIX_DISPLAY_LEN]
    assert len(key.prefix) == PREFIX_DISPLAY_LEN


def test_generate_then_verify_round_trip() -> None:
    """A freshly minted key verifies against its own stored hash."""
    key = generate_api_key()
    assert verify_api_key(key.full_key, key.hashed_key) is True


def test_minted_keys_are_unique() -> None:
    """Two mints never collide on secret or hash."""
    a = generate_api_key()
    b = generate_api_key()
    assert a.full_key != b.full_key
    assert a.hashed_key != b.hashed_key


def test_hashing_is_deterministic() -> None:
    """Re-hashing the same key reproduces the stored digest."""
    key = generate_api_key()
    assert hash_api_key(key.full_key) == key.hashed_key


def test_verify_rejects_a_foreign_key() -> None:
    """A different key does not verify against another's hash."""
    key = generate_api_key()
    impostor = generate_api_key()
    assert verify_api_key(impostor.full_key, key.hashed_key) is False


def test_hash_is_sha256_hex_digest() -> None:
    """The digest is 64 hex chars (SHA-256)."""
    key = generate_api_key()
    assert len(key.hashed_key) == 64
    int(key.hashed_key, 16)  # raises if not valid hex


def test_extract_prefix_matches_generated_prefix() -> None:
    """``extract_prefix`` agrees with the prefix produced at generation."""
    key = generate_api_key()
    assert extract_prefix(key.full_key) == key.prefix


# --- Password hashing ---------------------------------------------------


def test_password_hash_then_verify_round_trip() -> None:
    """A password verifies against its own bcrypt hash."""
    hashed = hash_password("Sup3r-Secret!")
    assert verify_password("Sup3r-Secret!", hashed) is True


def test_verify_rejects_wrong_password() -> None:
    """A different password does not verify against the hash."""
    hashed = hash_password("Sup3r-Secret!")
    assert verify_password("not-it", hashed) is False


def test_password_hashing_is_salted() -> None:
    """Hashing the same password twice yields distinct hashes."""
    assert hash_password("same") != hash_password("same")


def test_verify_handles_malformed_hash() -> None:
    """A malformed stored hash yields False rather than raising."""
    assert verify_password("whatever", "not-a-bcrypt-hash") is False


def test_long_password_beyond_bcrypt_limit() -> None:
    """Passwords longer than bcrypt's 72-byte limit hash in full.

    Two long passwords that share their first 72 bytes must not collide,
    proving the SHA-256 pre-hash consumes the whole input.
    """
    base = "x" * 80
    hashed = hash_password(base + "-alpha")
    assert verify_password(base + "-alpha", hashed) is True
    assert verify_password(base + "-omega", hashed) is False


# --- Access tokens (JWT) ------------------------------------------------


def test_access_token_round_trip_carries_subject_and_role() -> None:
    """A minted token decodes back to its subject and role claims."""
    token = create_access_token(subject="agent-123", role="MANAGER")
    claims = decode_access_token(token)
    assert claims["sub"] == "agent-123"
    assert claims["role"] == "MANAGER"


def test_expired_access_token_is_rejected() -> None:
    """A token past its expiry fails to decode."""
    token = create_access_token(
        subject="agent-123",
        role="AGENT",
        expires_delta=timedelta(minutes=-1),
    )
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_tampered_access_token_is_rejected() -> None:
    """A token with a mutated signature fails to decode."""
    token = create_access_token(subject="agent-123", role="AGENT")
    tampered = token[:-4] + ("aaaa" if token[-4:] != "aaaa" else "bbbb")
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(tampered)
