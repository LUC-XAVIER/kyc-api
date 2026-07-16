"""Production secret enforcement in Settings.

These build Settings directly rather than using the module-level `settings`,
which is lru_cached at import and reflects the developer's own .env.
"""

import pytest

from app.core.config import INSECURE_DEFAULT, MIN_SECRET_BYTES, Settings

STRONG = "x" * MIN_SECRET_BYTES


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch):
    """Hide the developer's real secrets so defaults are what's tested."""
    for name in ("SECRET_KEY", "API_KEY_PEPPER", "ENVIRONMENT"):
        monkeypatch.delenv(name, raising=False)


def build(**overrides) -> Settings:
    """Settings with .env ignored, so only overrides + defaults apply."""
    return Settings(_env_file=None, **overrides)


def test_development_tolerates_weak_secrets():
    """The dev default must keep working — this is the local-dev path."""
    cfg = build(environment="development")
    assert cfg.secret_key == INSECURE_DEFAULT
    assert not cfg.is_production


def test_production_rejects_placeholder_secret_key():
    """A forgotten SECRET_KEY lets anyone forge session tokens."""
    with pytest.raises(ValueError, match="SECRET_KEY"):
        build(environment="production", api_key_pepper=STRONG)


def test_production_rejects_placeholder_pepper():
    """A known pepper makes stored API-key digests reproducible."""
    with pytest.raises(ValueError, match="API_KEY_PEPPER"):
        build(environment="production", secret_key=STRONG)


def test_production_rejects_short_secret_key():
    """Set-but-too-short is the subtler failure: it looks configured."""
    with pytest.raises(ValueError, match="SECRET_KEY"):
        build(
            environment="production",
            secret_key="x" * (MIN_SECRET_BYTES - 1),
            api_key_pepper=STRONG,
        )


def test_production_reports_every_offender_at_once():
    """One restart per missing variable is a miserable way to deploy."""
    with pytest.raises(ValueError) as err:
        build(environment="production")
    assert "SECRET_KEY" in str(err.value)
    assert "API_KEY_PEPPER" in str(err.value)


def test_production_accepts_strong_secrets():
    """The happy path: a properly configured deploy boots."""
    cfg = build(
        environment="production", secret_key=STRONG, api_key_pepper=STRONG
    )
    assert cfg.is_production


def test_environment_name_is_case_insensitive():
    """PRODUCTION in a deploy manifest must not silently skip the check."""
    with pytest.raises(ValueError):
        build(environment="PRODUCTION")
