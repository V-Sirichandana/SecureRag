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
