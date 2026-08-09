from __future__ import annotations

from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.paths import resolve_env_files

# Known-insecure placeholder shipped in .env.example — must never be used at runtime.
INSECURE_SECRET_KEY_DEFAULT = "change-me-in-production-use-long-random-string"
MIN_SECRET_KEY_LENGTH = 32


class Settings(BaseSettings):
    # env_file is applied in get_settings() via resolve_env_files() so native installs
    # can load %PROGRAMDATA%\…\config\.env without depending on process cwd.
    model_config = SettingsConfigDict(env_file_encoding="utf-8", extra="ignore")

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
    # Optional public metadata (posters / catalog harvest). Ranking does not depend on these.
    tmdb_api_key: str = ""
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
    # Feed generation is expensive (candidate retrieval + scoring + event writes), so
    # cap how often a single authenticated user can regenerate a feed.
    feed_rate_limit_per_minute: int = 30           # per authenticated user
    # Cap how many of a user's most-recent interactions are folded into their taste
    # profile on each feed generation. Bounds profile-building time and memory so a
    # long-lived account with a huge interaction history doesn't degrade feed latency.
    profile_max_interactions: int = 5000
    # RecommendationEvent rows are written on every feed generation. Prune rows for a
    # (user, feed) older than this on each generation so the table can't grow unbounded.
    # Keep generous: offline metrics are computed from these rows. 0 disables pruning.
    recommendation_event_retention_days: int = 90
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
    # Native packaging: directory with Vite ``dist`` (index.html). Empty = API-only
    # (Docker nginx / Vite dev still serve the UI separately). See docs/packaging/adr-serve-web.md.
    web_dist_dir: str = ""

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
    env_files = resolve_env_files()
    if env_files:
        return Settings(_env_file=env_files)
    # No dotenv on disk: rely on process environment only (CI, some containers).
    return Settings(_env_file=None)
