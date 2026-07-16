"""AES-GCM sealing of personal data at rest (NFR03/NFR04)."""

import base64

import pytest

from app.core import crypto
from app.core.crypto import DecryptionError, decrypt, encrypt, generate_key


@pytest.fixture(autouse=True)
def _key(monkeypatch):
    """Configure a real key and clear the cipher cache around each test."""
    crypto._cipher.cache_clear()
    monkeypatch.setattr(
        crypto.settings, "encryption_key", generate_key(), raising=False
    )
    yield
    crypto._cipher.cache_clear()


def test_round_trip_returns_the_original_bytes():
    """The basic contract."""
    assert decrypt(encrypt(b"Luc-Xavier Foning")) == b"Luc-Xavier Foning"


def test_ciphertext_does_not_contain_the_plaintext():
    """A database dump must not leak the value it stores."""
    assert b"AA14700081" not in encrypt(b"AA14700081")


def test_same_plaintext_encrypts_differently_each_time():
    """Equal values must not produce equal ciphertext.

    The nonce is random per write; deterministic encryption would reveal
    which clients share a name or a birthplace.
    """
    assert encrypt(b"Douala") != encrypt(b"Douala")


def test_tampered_ciphertext_is_rejected():
    """GCM authenticates: a flipped byte fails loudly, not silently."""
    blob = bytearray(encrypt(b"1990-01-01"))
    blob[-1] ^= 0x01
    with pytest.raises(DecryptionError):
        decrypt(bytes(blob))


def test_value_from_another_key_is_rejected(monkeypatch):
    """Rotating the key makes old rows unreadable — loudly, not as garbage."""
    blob = encrypt(b"secret")
    crypto._cipher.cache_clear()
    monkeypatch.setattr(crypto.settings, "encryption_key", generate_key())
    with pytest.raises(DecryptionError):
        decrypt(blob)


def test_unrecognised_envelope_is_rejected():
    """Plaintext left in the column by a bad migration must not decode."""
    with pytest.raises(DecryptionError):
        decrypt(b"not-an-envelope")


def test_empty_plaintext_round_trips():
    """An empty OCR field is distinct from a NULL one."""
    assert decrypt(encrypt(b"")) == b""


def test_missing_key_is_a_clear_error(monkeypatch):
    """Failing to configure the key must not be a confusing crash."""
    crypto._cipher.cache_clear()
    monkeypatch.setattr(crypto.settings, "encryption_key", "")
    with pytest.raises(ValueError, match="ENCRYPTION_KEY is not set"):
        encrypt(b"x")


def test_wrong_length_key_is_rejected(monkeypatch):
    """A 16-byte key would silently give AES-128, not the AES-256 claimed."""
    crypto._cipher.cache_clear()
    short = base64.urlsafe_b64encode(b"x" * 16).decode()
    monkeypatch.setattr(crypto.settings, "encryption_key", short)
    with pytest.raises(ValueError, match="must decode to 32 bytes"):
        encrypt(b"x")


def test_generate_key_is_usable_and_unique():
    """Operators bootstrap deployments with this."""
    assert generate_key() != generate_key()
    assert len(base64.urlsafe_b64decode(generate_key())) == 32
