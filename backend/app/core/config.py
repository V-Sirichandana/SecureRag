"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import parse_qsl, urlencode

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET_WARNING = (
    "JWT_SECRET_KEY is not set; using an ephemeral development secret. "
    "Tokens will not survive a restart. Set JWT_SECRET_KEY in production."
)

# public OpenAI-compatible endpoint — never a secret; override with LLM_BASE_URL
# to target any other OpenAI-compatible server (local or self-hosted).
DEFAULT_LLM_BASE_URL = "https://api.openai.com/v1"


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
    jwt_secret_key: str = Field(default="", repr=False)
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
    qdrant_api_key: str = Field(default="", repr=False)
    qdrant_collection: str = "securerag"
    embedding_provider: str = "hashing"
    embedding_model: str = ""
    embedding_dim: int = Field(default=384, ge=8, le=8192)
    embedding_cache_dir: str = ""
    chunk_size: int = Field(default=800, ge=100)
    chunk_overlap: int = Field(default=120, ge=0)
    storage_dir: str = "data/uploads"
    storage_provider: str = "local"
    storage_bucket: str = ""
    storage_endpoint_url: str = ""
    storage_region: str = ""
    storage_access_key_id: str = Field(default="", repr=False)
    storage_secret_access_key: str = Field(default="", repr=False)
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    llm_provider: str = ""
    llm_api_key: str = Field(default="", repr=False)
    llm_model: str = ""
    llm_base_url: str = DEFAULT_LLM_BASE_URL
    llm_timeout_seconds: float = Field(default=30.0, ge=1, le=300)

    # reranker
    reranker_provider: str = "heuristic"
    reranker_model: str = ""
    reranker_top_k: int = Field(default=5, ge=1)
    reranker_max_candidates: int = Field(default=40, ge=1)

    # retrieval mode (server-side only — never accepted from clients)
    retrieval_mode: str = "vector"

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

    @model_validator(mode="after")
    def _validate_production_hardening(self) -> Settings:
        if not self.is_production:
            return self
        if self.debug:
            raise ValueError("DEBUG must be false when APP_ENV=production")
        if "*" in self.cors_origins_list:
            raise ValueError(
                "CORS_ORIGINS must not contain '*' when APP_ENV=production "
                "(credentialed requests require explicit origins)"
            )
        return self

    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        """Accept the URL shapes copied from Render / Neon dashboards.

        Dashboards hand out ``postgresql://…?sslmode=require`` (and users
        sometimes paste the whole ``DATABASE_URL=…`` line, quotes included).
        SQLAlchemy's asyncpg driver expects ``postgresql+asyncpg://`` and an
        ``ssl`` query parameter, so normalise those here.  The error message
        never includes the value.
        """
        url = (value or "").strip()
        # Accept both ``DATABASE_URL="…"`` and ``"DATABASE_URL=…"`` paste shapes.
        for _ in range(2):
            if url[:13].lower() == "database_url=":
                url = url.split("=", 1)[1].strip()
            if len(url) >= 2 and url[0] == url[-1] and url[0] in {'"', "'"}:
                url = url[1:-1].strip()
        if not url:
            raise ValueError(
                "DATABASE_URL is empty; set it to a PostgreSQL connection URL"
            )
        if url.startswith("postgres://"):
            url = "postgresql+asyncpg://" + url[len("postgres://") :]
        elif url.startswith("postgresql://"):
            url = "postgresql+asyncpg://" + url[len("postgresql://") :]
        if url.startswith("postgresql+asyncpg://"):
            base, _, query = url.partition("?")
            params: dict[str, str] = {}
            for key, query_value in parse_qsl(query, keep_blank_values=True):
                lowered = key.lower()
                if lowered == "channel_binding":
                    continue
                params["ssl" if lowered == "sslmode" else key] = query_value
            # Neon's pooled endpoint is PgBouncer in transaction mode, which
            # cannot reuse asyncpg's server-side prepared statements.
            if "-pooler" in base.rsplit("@", 1)[-1] and (
                "prepared_statement_cache_size" not in params
            ):
                params["prepared_statement_cache_size"] = "0"
            url = base + (("?" + urlencode(params)) if params else "")
        return url

    @field_validator("embedding_provider")
    @classmethod
    def _normalize_embedding_provider(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if not normalized:
            raise ValueError("EMBEDDING_PROVIDER must not be empty")
        return normalized

    @field_validator("embedding_model", "embedding_cache_dir")
    @classmethod
    def _strip_embedding_option(cls, value: str) -> str:
        return (value or "").strip()

    @field_validator("cookie_samesite")
    @classmethod
    def _validate_samesite(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"lax", "strict", "none"}:
            raise ValueError("cookie_samesite must be lax, strict or none")
        return normalized

    @field_validator("retrieval_mode")
    @classmethod
    def _validate_retrieval_mode(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in {"vector", "hybrid"}:
            raise ValueError("RETRIEVAL_MODE must be vector or hybrid")
        return normalized

    @field_validator("storage_provider")
    @classmethod
    def _validate_storage_provider(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in {"local", "s3"}:
            raise ValueError("STORAGE_PROVIDER must be local or s3")
        return normalized

    @field_validator(
        "storage_bucket",
        "storage_endpoint_url",
        "storage_region",
        "storage_access_key_id",
        "storage_secret_access_key",
    )
    @classmethod
    def _strip_storage_option(cls, value: str) -> str:
        return (value or "").strip()

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
