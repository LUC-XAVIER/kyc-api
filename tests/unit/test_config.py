"""Production secret enforcement in Settings.

These build Settings directly rather than using the module-level `settings`,
which is lru_cached at import and reflects the developer's own .env.
"""

import pytest

from app.core.config import INSECURE_DEFAULT, MIN_SECRET_BYTES, Settings
from app.core.crypto import generate_key

STRONG = "x" * MIN_SECRET_BYTES


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Hide the developer's real secrets so defaults are what's tested."""
    for name in (
        "SECRET_KEY",
        "API_KEY_PEPPER",
        "ENCRYPTION_KEY",
        "ENVIRONMENT",
    ):
        monkeypatch.delenv(name, raising=False)


def build(**overrides) -> Settings:
    """Settings with .env ignored, so only overrides + defaults apply."""
    return Settings(_env_file=None, **overrides)


def prod(**overrides) -> Settings:
    """A production Settings with every guarded secret strong.

    Tests weaken exactly one, so a failure names the field under test
    rather than whichever guarded secret happened to be left unset.
    """
    values = {
        "environment": "production",
        "secret_key": STRONG,
        "api_key_pepper": STRONG,
        "encryption_key": STRONG,
    }
    values.update(overrides)
    return build(**values)


def test_development_tolerates_weak_secrets():
    """The dev default must keep working — this is the local-dev path."""
    cfg = build(environment="development")
    assert cfg.secret_key == INSECURE_DEFAULT
    assert not cfg.is_production


def test_production_rejects_placeholder_secret_key():
    """A forgotten SECRET_KEY lets anyone forge session tokens."""
    with pytest.raises(ValueError, match="SECRET_KEY"):
        prod(secret_key=INSECURE_DEFAULT)


def test_production_rejects_placeholder_pepper():
    """A known pepper makes stored API-key digests reproducible."""
    with pytest.raises(ValueError, match="API_KEY_PEPPER"):
        prod(api_key_pepper=INSECURE_DEFAULT)


def test_production_rejects_unset_encryption_key():
    """Without it the PII columns cannot be sealed at all (NFR03/NFR04)."""
    with pytest.raises(ValueError, match="ENCRYPTION_KEY"):
        prod(encryption_key="")


def test_production_rejects_short_secret_key():
    """Set-but-too-short is the subtler failure: it looks configured."""
    with pytest.raises(ValueError, match="SECRET_KEY"):
        prod(secret_key="x" * (MIN_SECRET_BYTES - 1))


def test_production_reports_every_offender_at_once():
    """One restart per missing variable is a miserable way to deploy."""
    with pytest.raises(ValueError) as err:
        build(environment="production")
    message = str(err.value)
    assert "SECRET_KEY" in message
    assert "API_KEY_PEPPER" in message
    assert "ENCRYPTION_KEY" in message


def test_production_accepts_strong_secrets():
    """The happy path: a properly configured deploy boots."""
    assert prod().is_production


def test_environment_name_is_case_insensitive():
    """PRODUCTION in a deploy manifest must not silently skip the check."""
    with pytest.raises(ValueError):
        build(environment="PRODUCTION")


def test_encryption_key_from_generate_key_passes_the_guard():
    """The documented bootstrap path must satisfy the check it feeds."""
    assert prod(encryption_key=generate_key()).is_production
