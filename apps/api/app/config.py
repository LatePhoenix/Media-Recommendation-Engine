from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Known-insecure placeholder shipped in .env.example — must never be used at runtime.
INSECURE_SECRET_KEY_DEFAULT = "change-me-in-production-use-long-random-string"
MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://mediarec:mediarec@localhost:5432/mediarec"
    redis_url: str = "redis://localhost:6379/0"
    # No default: the app must refuse to start without an explicit, strong signing key.
    api_secret_key: str
    api_cors_origins: str = "http://localhost:5173,http://localhost:3000"
    access_token_expire_minutes: int = 60 * 12  # 12h; shorten further once refresh tokens exist
    credentials_fernet_key: str = ""
    # Comma-separated previously-active Fernet keys, kept only for decryption during
    # key rotation (MultiFernet). New ciphertext is always written with the primary key.
    credentials_fernet_keys_old: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_embed_model: str = "nomic-embed-text"
    enrichment_enabled: bool = False
    pass_cooldown_days: int = 14
    onboarding_min_ratings: int = 10
    # When the RQ queue is unavailable, only run imports inline (in the request thread)
    # if this is explicitly enabled — intended for local dev without a worker. In
    # production leave it False so the API never blocks on a long external sync.
    allow_inline_import_sync: bool = False
    inline_import_timeout_seconds: int = 60
    # Auth rate limiting (brute-force / mass-registration protection).
    login_rate_limit_per_minute: int = 10          # per client IP
    login_rate_limit_per_username_per_minute: int = 5
    register_rate_limit_per_hour: int = 20         # per client IP
    # Only honor X-Forwarded-For when the app runs behind a trusted proxy that sets it;
    # otherwise clients could spoof the header to evade per-IP limits.
    trust_proxy_headers: bool = False
    # Local-first: allow RFC1918/loopback for import source base_urls (Plex/Jellyfin).
    # Link-local / cloud metadata remain blocked. Set false for internet-exposed deploys.
    allow_private_import_urls: bool = True
    # When false, /register returns 403 (after first-user bootstrap use this to lock signup).
    registration_enabled: bool = True
    # When true, rate-limiter backend errors allow the request; default fail-closed (503).
    rate_limit_fail_open: bool = False

    @field_validator("api_secret_key")
    @classmethod
    def _reject_insecure_secret_key(cls, v: str) -> str:
        if not v or v == INSECURE_SECRET_KEY_DEFAULT or len(v) < MIN_SECRET_KEY_LENGTH:
            raise ValueError(
                "API_SECRET_KEY must be set to a random value of at least "
                f"{MIN_SECRET_KEY_LENGTH} characters and must not be the placeholder from "
                ".env.example. Generate one with: "
                "python -c \"import secrets; print(secrets.token_urlsafe(48))\""
            )
        return v

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
