"""Reranker configuration: defaults, custom values, load-time validation, factory."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.exceptions import ServiceNotConfiguredError
from app.services.rag import get_reranker
from app.services.rag.reranker import HeuristicReranker


def test_reranker_defaults():
    settings = Settings(_env_file=None)
    assert settings.reranker_provider == "heuristic"
    assert settings.reranker_model == ""
    assert settings.reranker_top_k == 5
    assert settings.reranker_max_candidates == 40


def test_valid_custom_configuration():
    settings = Settings(
        reranker_provider="heuristic", reranker_top_k=10, reranker_max_candidates=30
    )
    assert settings.reranker_provider == "heuristic"
    assert settings.reranker_top_k == 10
    assert settings.reranker_max_candidates == 30


def test_empty_model_is_accepted():
    settings = Settings(reranker_model="")
    assert settings.reranker_model == ""


def test_invalid_reranker_top_k_rejected():
    with pytest.raises(ValidationError):
        Settings(reranker_top_k=0)


def test_invalid_max_candidates_rejected():
    with pytest.raises(ValidationError):
        Settings(reranker_max_candidates=0)


def test_top_k_above_max_candidates_rejected():
    with pytest.raises(ValidationError) as excinfo:
        Settings(reranker_top_k=50, reranker_max_candidates=40)
    assert "RERANKER_TOP_K must not exceed RERANKER_MAX_CANDIDATES" in str(excinfo.value)


def test_factory_resolves_configured_heuristic():
    settings = Settings(reranker_provider="heuristic")
    assert isinstance(get_reranker(settings), HeuristicReranker)


def test_factory_rejects_unknown_provider():
    settings = Settings(reranker_provider="does-not-exist")
    with pytest.raises(ServiceNotConfiguredError) as excinfo:
        get_reranker(settings)
    assert excinfo.value.status_code == 501
    assert "does-not-exist" in str(excinfo.value)


# ------------------------------------------------------------- retrieval mode
def test_retrieval_mode_defaults_to_vector():
    settings = Settings(_env_file=None)
    assert settings.retrieval_mode == "vector"


def test_retrieval_mode_accepts_vector():
    settings = Settings(retrieval_mode="vector")
    assert settings.retrieval_mode == "vector"


def test_retrieval_mode_accepts_hybrid():
    settings = Settings(retrieval_mode="hybrid")
    assert settings.retrieval_mode == "hybrid"


def test_retrieval_mode_is_normalized():
    settings = Settings(retrieval_mode="Hybrid")
    assert settings.retrieval_mode == "hybrid"


@pytest.mark.parametrize("mode", ["bm25", "lexical", "anything"])
def test_invalid_retrieval_mode_rejected(mode):
    with pytest.raises(ValidationError) as excinfo:
        Settings(retrieval_mode=mode)
    assert "RETRIEVAL_MODE must be vector or hybrid" in str(excinfo.value)


def test_embedding_configuration_is_normalized():
    settings = Settings(
        embedding_provider=" FastEmbed ",
        embedding_model=" BAAI/bge-small-en-v1.5 ",
        embedding_cache_dir=" /var/cache/fastembed ",
        embedding_dim=384,
    )
    assert settings.embedding_provider == "fastembed"
    assert settings.embedding_model == "BAAI/bge-small-en-v1.5"
    assert settings.embedding_cache_dir == "/var/cache/fastembed"
    assert settings.embedding_dim == 384


def test_empty_embedding_provider_is_rejected():
    with pytest.raises(ValidationError) as excinfo:
        Settings(embedding_provider="  ")
    assert "EMBEDDING_PROVIDER must not be empty" in str(excinfo.value)


@pytest.mark.parametrize("dimension", [0, 7, 8193])
def test_embedding_dimension_bounds_are_enforced(dimension):
    with pytest.raises(ValidationError):
        Settings(embedding_dim=dimension)


def test_production_rejects_debug_mode():
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            _env_file=None,
            app_env="production",
            jwt_secret_key="prod-secret-key-for-tests-only-0123",
            debug=True,
        )
    assert "DEBUG must be false when APP_ENV=production" in str(excinfo.value)


def test_production_rejects_wildcard_cors():
    with pytest.raises(ValidationError) as excinfo:
        Settings(
            _env_file=None,
            app_env="production",
            jwt_secret_key="prod-secret-key-for-tests-only-0123",
            cors_origins="https://app.example.com,*",
        )
    assert "CORS_ORIGINS must not contain '*'" in str(excinfo.value)


def test_production_accepts_explicit_safe_configuration():
    settings = Settings(
        _env_file=None,
        app_env="production",
        jwt_secret_key="prod-secret-key-for-tests-only-0123",
        debug=False,
        cors_origins="https://app.example.com,https://admin.example.com",
    )
    assert settings.is_production
    assert settings.debug is False
    assert settings.cors_origins_list == [
        "https://app.example.com",
        "https://admin.example.com",
    ]


def test_development_still_allows_debug_mode():
    settings = Settings(_env_file=None, app_env="development", debug=True)
    assert settings.debug is True


def test_render_style_database_url_is_normalized():
    settings = Settings(
        _env_file=None,
        database_url=(
            "postgresql://user:pass@example.neon.tech/neondb"
            "?sslmode=require&channel_binding=require"
        ),
    )
    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert "ssl=require" in settings.database_url
    assert "sslmode" not in settings.database_url
    assert "channel_binding" not in settings.database_url


def test_neon_pooled_database_url_disables_prepared_statements():
    settings = Settings(
        _env_file=None,
        database_url=(
            "postgresql://user:pass@ep-example-pooler.c-2.sa-east-1.aws.neon.tech"
            "/neondb?sslmode=require"
        ),
    )
    assert "ssl=require" in settings.database_url
    assert "prepared_statement_cache_size=0" in settings.database_url


def test_database_url_with_quotes_and_env_prefix_is_normalized():
    settings = Settings(
        _env_file=None,
        database_url='"DATABASE_URL=postgres://user:pass@example.neon.tech/neondb"',
    )
    assert settings.database_url == (
        "postgresql+asyncpg://user:pass@example.neon.tech/neondb"
    )


def test_sqlite_database_url_is_unchanged():
    settings = Settings(
        _env_file=None, database_url="sqlite+aiosqlite:///:memory:"
    )
    assert settings.database_url == "sqlite+aiosqlite:///:memory:"


def test_empty_database_url_is_rejected():
    with pytest.raises(ValidationError) as excinfo:
        Settings(_env_file=None, database_url="   ")
    assert "DATABASE_URL is empty" in str(excinfo.value)


def test_secret_settings_are_not_in_repr():
    settings = Settings(
        _env_file=None,
        jwt_secret_key="jwt-secret-value",
        qdrant_api_key="qdrant-secret-value",
        llm_api_key="llm-secret-value",
    )
    rendered = repr(settings)
    for secret in ("jwt-secret-value", "qdrant-secret-value", "llm-secret-value"):
        assert secret not in rendered
