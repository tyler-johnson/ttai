"""
Configuration management for TTAI workers.

Loads settings from environment variables with sensible defaults
for local development.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env.local",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # TastyTrade
    tt_client_secret: str = Field(default="", description="TastyTrade OAuth client/provider secret")
    tt_refresh_token: str = Field(default="", description="TastyTrade refresh token")

    # Redis
    redis_url: str = Field(
        default="redis://:devpassword@localhost:6379",
        description="Redis connection URL",
    )

    # PostgreSQL
    database_url: str = Field(
        default="postgresql://ttai:devpassword@localhost:5432/ttai",
        description="PostgreSQL connection URL",
    )

    # Temporal
    temporal_address: str = Field(
        default="localhost:7233",
        description="Temporal server address",
    )
    temporal_namespace: str = Field(
        default="default",
        description="Temporal namespace",
    )
    temporal_task_queue: str = Field(
        default="ttai-queue",
        description="Temporal task queue name",
    )

    # Cache TTLs (in seconds)
    quote_cache_ttl: int = Field(
        default=5,
        description="TTL for cached quotes in seconds",
    )

    # Database pool settings
    db_pool_min_size: int = Field(default=2, description="Minimum database pool connections")
    db_pool_max_size: int = Field(default=10, description="Maximum database pool connections")


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
