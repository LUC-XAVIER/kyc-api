"""Unit tests for the API-key security primitives (no DB)."""

from app.core.security import (
    KEY_PREFIX,
    PREFIX_DISPLAY_LEN,
    extract_prefix,
    generate_api_key,
    hash_api_key,
    verify_api_key,
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
