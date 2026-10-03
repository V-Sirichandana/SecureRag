"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET_WARNING = (
    "JWT_SECRET_KEY is not set; using an ephemeral development secret. "
    "Tokens will not survive a restart. Set JWT_SECRET_KEY in production."
)


class Settings(BaseSettings):
    """Environment-driven settings.

    Every field can be overridden through an environment variable of the same
    name (case-insensitive) or a local ``.env`` file. Real secrets are never
    committed to git — see ``.env.example`` for the variable list.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # runtime
    app_env: str = "development"
    debug: bool = False
    project_name: str = "SecureRAG API"
    api_v1_prefix: str = "/api/v1"
    log_level: str = "INFO"

    # database / cache
    database_url: str = "postgresql+asyncpg://securerag:securerag@localhost:5432/securerag"
    redis_url: str = ""

    # authentication
    jwt_secret_key: str = ""
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = Field(default=30, ge=1)
    refresh_token_expire_days: int = Field(default=14, ge=1)

    # cookies
    cookie_secure: bool = False
    cookie_samesite: str = "lax"

    # cors
    cors_origins: str = "http://localhost:3000"

    # rag providers (modular)
    qdrant_url: str = ""
    qdrant_api_key: str = ""
    qdrant_collection: str = "securerag"
    embedding_provider: str = "hashing"
    embedding_model: str = ""
    embedding_dim: int = Field(default=384, ge=8)
    chunk_size: int = Field(default=800, ge=100)
    chunk_overlap: int = Field(default=120, ge=0)
    storage_dir: str = "data/uploads"
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    llm_provider: str = ""
    llm_api_key: str = ""

    # reranker
    reranker_provider: str = "heuristic"
    reranker_model: str = ""
    reranker_top_k: int = Field(default=5, ge=1)
    reranker_max_candidates: int = Field(default=40, ge=1)

    # rate limiting
    rate_limit_login_attempts: int = Field(default=5, ge=1)
    rate_limit_login_window_seconds: int = Field(default=60, ge=1)

    @model_validator(mode="after")
    def _validate_chunking(self) -> Settings:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        return self

    @model_validator(mode="after")
    def _validate_reranker(self) -> Settings:
        if self.reranker_top_k > self.reranker_max_candidates:
            raise ValueError("RERANKER_TOP_K must not exceed RERANKER_MAX_CANDIDATES")
        return self

    @field_validator("cookie_samesite")
    @classmethod
    def _validate_samesite(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("cookie_samesite must be lax, strict or none")
        return normalized

    @property
    def cors_origins_list(self) -> list[str]:
        """Parse the comma-separated CORS_ORIGINS value."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env.strip().lower() in {"production", "prod"}

    @property
    def uses_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance (env is read once)."""
    return Settings()
