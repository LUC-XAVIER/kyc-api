"""Application configuration loaded from environment variables.

All sensitive configuration (database credentials, secret keys) is read
from the environment and never hardcoded, per Design doc §4.2.2.
"""

from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Placeholder shipped as the dev default; must never survive into production.
INSECURE_DEFAULT = "change-me-in-production"

# RFC 7518 §3.2: an HMAC-SHA256 key must be at least as long as the digest.
MIN_SECRET_BYTES = 32


class Settings(BaseSettings):
    """Typed application settings sourced from the environment / .env file."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Application ---
    app_name: str = "KYC-API"
    environment: str = Field(default="development")
    debug: bool = Field(default=False)
    api_v1_prefix: str = "/api/v1"

    # --- Security ---
    secret_key: str = Field(default="change-me-in-production")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    # Server-side pepper mixed into API-key hashing.
    api_key_pepper: str = Field(default="change-me-in-production")

    # --- Database ---
    database_url: str = Field(
        default="postgresql+psycopg://kyc:kyc@localhost:5432/kyc"
    )

    # --- Pipeline thresholds (tunable; see Design doc §6.3.1) ---
    face_match_threshold: float = 0.40
    liveness_threshold: float = 0.50
    duplicate_threshold: float = 0.70
    pipeline_timeout_seconds: int = 10  # NFR01

    # --- Storage paths ---
    faiss_index_path: str = "faiss_index/index.faiss"
    antispoof_model_path: str = "models/antispoof_svm.pkl"

    # --- CORS (Angular dashboard dev-server origin) ---
    cors_origins: list[str] = [
        "http://localhost:4200",
        "http://127.0.0.1:4200",
    ]

    # --- Subscription enforcement (Design doc §6.2) ---
    quota_warning_ratio: float = 0.80

    # --- Onboarding / email ---
    # Where the dashboard lives, for the links we email (signup, PIN reset).
    dashboard_url: str = "http://localhost:4200"
    signup_token_ttl_hours: int = 48
    reset_token_ttl_hours: int = 2
    # When email is disabled (dev), links are logged and returned by the
    # API instead of sent. Set email_enabled=true + SMTP creds for real mail.
    email_enabled: bool = True
    # Must match the authenticated SMTP account or the provider will reject
    # or rewrite it — set EMAIL_FROM in .env, never hardcode a real address.
    email_from: str = "KYC-API <no-reply@kyc-api.local>"
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    @property
    def is_production(self) -> bool:
        """True when running under the production environment name."""
        return self.environment.lower() == "production"

    @model_validator(mode="after")
    def _reject_weak_secrets(self) -> "Settings":
        """Fail fast if production is running on dev-grade secrets.

        Guards secret_key (signs dashboard JWTs) and api_key_pepper (mixed
        into the API-key digest). Outside production the weak defaults are
        allowed, so local dev and tests keep working untouched.

        Raises:
            ValueError: if a guarded secret is the shipped placeholder or is
                shorter than MIN_SECRET_BYTES, listing every offender at once
                so a deploy isn't fixed one variable per restart.
        """
        if self.is_production:
            guarded = (
                ("SECRET_KEY", self.secret_key),
                ("API_KEY_PEPPER", self.api_key_pepper),
            )
            weak = [
                name
                for name, value in guarded
                if value == INSECURE_DEFAULT
                or len(value.encode()) < MIN_SECRET_BYTES
            ]
            if weak:
                raise ValueError(
                    f"Insecure {', '.join(weak)} in production: set a "
                    f"random value of at least {MIN_SECRET_BYTES} bytes."
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()


settings = get_settings()
