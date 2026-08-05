from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "postgresql+psycopg://mediarec:mediarec@localhost:5432/mediarec"
    redis_url: str = "redis://localhost:6379/0"
    api_secret_key: str = "change-me-in-production-use-long-random-string"
    api_cors_origins: str = "http://localhost:5173,http://localhost:3000"
    access_token_expire_minutes: int = 60 * 24 * 7
    credentials_fernet_key: str = ""
    ollama_base_url: str = "http://localhost:11434"
    ollama_embed_model: str = "nomic-embed-text"
    enrichment_enabled: bool = False
    pass_cooldown_days: int = 14
    onboarding_min_ratings: int = 10

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.api_cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
