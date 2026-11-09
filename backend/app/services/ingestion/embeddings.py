"""Embedding providers behind the :class:`EmbeddingService` protocol.

The application never talks to a provider directly — it asks the factory in
``app.services.rag`` for the configured implementation. Two providers ship:

* ``hashing``   deterministic feature hashing, zero downloads (dev/tests)
* ``fastembed`` local semantic model through FastEmbed (optional extra)

The default provider remains ``hashing``. ``fastembed`` validates the model
name and vector dimension against FastEmbed's *actual* model metadata before
any download/load, loads the model lazily on the first embedding call, and
keeps a small process-wide model cache so every request does not reload ONNX
weights. Both query and document embeddings go through the same validated
model and dimension; output vectors are checked again before they reach the
index or a Qdrant query.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import math
import re
import threading
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from app.core.exceptions import AppError, ServiceNotConfiguredError
from app.services.rag.base import EmbeddingService

logger = logging.getLogger("securerag.embeddings")

HASHING_PROVIDER_NAME = "hashing"
FASTEMBED_PROVIDER_NAME = "fastembed"

# FastEmbed's current supported dense model with the same 384-dimensional
# shape as the hashing default. It is only used when EMBEDDING_MODEL is empty.
DEFAULT_FASTEMBED_MODEL = "BAAI/bge-small-en-v1.5"
DEFAULT_FASTEMBED_DIMENSION = 384
FASTEMBED_MIN_VERSION = "0.4.2"

# Bounded process-wide model cache. Construction stays cheap and the first
# embedding call loads weights off the event loop.
_MAX_CACHED_MODELS = 2
_MODEL_CACHE: OrderedDict[tuple[Any, str, str | None], Any] = OrderedDict()
_MODEL_CACHE_LOCK = threading.Lock()

_TOKEN_RE = re.compile(r"\w+", re.UNICODE)


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


class HashingEmbeddingProvider:
    """Deterministic feature-hashing embeddings — no model download.

    Tokens and character trigrams are hashed into a fixed-width signed vector
    that is L2-normalized. Deterministic across processes and platforms, which
    makes it ideal for tests and offline development. It remains the default;
    setting ``EMBEDDING_PROVIDER=fastembed`` is required for semantic quality.
    """

    provider_name = HASHING_PROVIDER_NAME
    model_name = "hashing-v1"

    def __init__(self, *, dimension: int = 384) -> None:
        if dimension < 8:
            raise ValueError("embedding dimension must be >= 8")
        self._dimension = dimension

    @property
    def dimension(self) -> int:
        return self._dimension

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    # -------------------------------------------------------------- internals
    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self._dimension
        normalized = re.sub(r"\s+", " ", text.lower()).strip()
        for feature in self._features(normalized):
            digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimension
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign
        return _l2_normalize(vector)

    @staticmethod
    def _features(normalized: str) -> list[str]:
        features: list[str] = []
        for token in _TOKEN_RE.findall(normalized):
            features.append(f"w:{token}")
        # character trigrams keep some signal for scripts without word spaces
        padded = f" {normalized} "
        features.extend(
            f"c:{padded[index:index + 3]}" for index in range(len(padded) - 2)
        )
        return features


# Optional test/extension seam: when set, this class is used instead of
# importing FastEmbed. Production leaves it as ``None``.
TextEmbedding: type | None = None


def _import_text_embedding() -> type:
    """Import FastEmbed's dense embedding class without loading a model.

    A missing (or broken) optional dependency is a configuration error (501);
    it is never silently replaced by the hashing provider.
    """
    if TextEmbedding is not None:
        return TextEmbedding
    try:
        from fastembed import TextEmbedding as imported
    except ImportError as exc:
        raise ServiceNotConfiguredError(
            "SERVICE_NOT_CONFIGURED",
            "EMBEDDING_PROVIDER=fastembed requires the 'fastembed' package "
            f"(pip install 'fastembed>={FASTEMBED_MIN_VERSION}').",
        ) from exc
    except Exception as exc:  # noqa: BLE001 - broken optional dependency
        raise ServiceNotConfiguredError(
            "SERVICE_NOT_CONFIGURED",
            "FastEmbed could not be initialized for semantic embeddings. "
            "Reinstall the optional dependency "
            f"(pip install 'fastembed>={FASTEMBED_MIN_VERSION}').",
        ) from exc
    return imported


def _is_fastembed_text_embedding(encoder_cls: type | None) -> bool:
    """Only share the real FastEmbed model across provider instances.

    Test doubles and custom factories stay private to their provider instance
    so independent tests/tenants cannot observe one another's mock state.
    """
    if encoder_cls is None:
        return False
    module = str(getattr(encoder_cls, "__module__", ""))
    return module == "fastembed" or module.startswith("fastembed.")


def _supported_model_descriptions(encoder_cls: type) -> list[Any] | None:
    """Return metadata entries, or ``None`` when the class exposes none."""
    lister = getattr(encoder_cls, "list_supported_models", None)
    if not callable(lister):
        return None
    try:
        descriptions = lister()
    except Exception as exc:  # noqa: BLE001 - metadata is part of configuration
        raise ServiceNotConfiguredError(
            "SERVICE_NOT_CONFIGURED",
            "FastEmbed's embedding model metadata could not be read. "
            "Reinstall the optional dependency.",
        ) from exc
    return list(descriptions or [])


def _description_value(description: Any, key: str) -> Any:
    if isinstance(description, dict):
        return description.get(key)
    return getattr(description, key, None)


def _metadata_dimension(description: Any) -> int | None:
    value = _description_value(description, "dim")
    try:
        dimension = int(value)
    except (TypeError, ValueError):
        return None
    return dimension if dimension > 0 else None


def fastembed_model_dimension(model_name: str, *, encoder_cls: type | None = None) -> int:
    """Look up a model's dimension from FastEmbed metadata, without loading it.

    Raises ``SERVICE_NOT_CONFIGURED`` (501) for an unsupported model or when
    the installed FastEmbed version exposes no usable metadata. This is used
    both at provider construction and by migration tooling.
    """
    cls = encoder_cls or _import_text_embedding()
    descriptions = _supported_model_descriptions(cls)
    if descriptions is not None:
        for description in descriptions:
            name = _description_value(description, "model")
            if isinstance(name, str) and name.strip().casefold() == model_name.casefold():
                dimension = _metadata_dimension(description)
                if dimension is None:
                    raise ServiceNotConfiguredError(
                        "SERVICE_NOT_CONFIGURED",
                        f"FastEmbed did not report a vector dimension for '{model_name}'.",
                    )
                return dimension
        raise ServiceNotConfiguredError(
            "SERVICE_NOT_CONFIGURED",
            f"EMBEDDING_MODEL '{model_name}' is not a supported FastEmbed "
            "embedding model. Check FastEmbed's list_supported_models().",
        )

    getter = getattr(cls, "get_embedding_size", None)
    if callable(getter):
        try:
            dimension = int(getter(model_name))
        except Exception as exc:  # noqa: BLE001 - normalize optional metadata
            raise ServiceNotConfiguredError(
                "SERVICE_NOT_CONFIGURED",
                f"EMBEDDING_MODEL '{model_name}' has no readable FastEmbed metadata.",
            ) from exc
        if dimension > 0:
            return dimension

    # Test doubles / custom FastEmbed-compatible classes may not expose model
    # metadata. The configured dimension is then the only contract available;
    # real FastEmbed always takes the branch above.
    raise ServiceNotConfiguredError(
        "SERVICE_NOT_CONFIGURED",
        "FastEmbed did not expose model metadata; cannot verify EMBEDDING_DIM.",
    )


class FastEmbedEmbeddingProvider:
    """Local semantic embeddings through FastEmbed (optional dependency).

    The model name and dimension are validated against FastEmbed metadata at
    construction time (no weights are downloaded). The actual model is created
    lazily on the first embedding call, off the event loop, and cached
    process-wide for real FastEmbed models. Failures are safe domain errors:

    * missing dependency / unsupported model / dimension mismatch → 501
    * model load or inference failure, malformed output → 503

    ``embed_query`` uses FastEmbed's query path and ``embed_documents`` its
    passage path when available, but both always share the same model instance
    and validated dimension.
    """

    provider_name = FASTEMBED_PROVIDER_NAME

    def __init__(
        self,
        *,
        model: str,
        dimension: int,
        cache_dir: str | None = None,
        encoder_factory: Callable[..., Any] | None = None,
    ) -> None:
        if dimension < 1:
            raise ValueError("embedding dimension must be positive")
        self.model_name = (model or "").strip() or DEFAULT_FASTEMBED_MODEL
        self.cache_dir = cache_dir
        self._encoder_factory = encoder_factory
        self._encoder_cls: type | None = None
        self._encoder: Any | None = None
        self._dimension = dimension

        if encoder_factory is None:
            self._encoder_cls = _import_text_embedding()
            metadata_dimension = fastembed_model_dimension(
                self.model_name, encoder_cls=self._encoder_cls
            )
            if metadata_dimension != dimension:
                raise ServiceNotConfiguredError(
                    "SERVICE_NOT_CONFIGURED",
                    f"EMBEDDING_DIM={dimension} does not match FastEmbed model "
                    f"'{self.model_name}' ({metadata_dimension} dimensions). "
                    "Set EMBEDDING_DIM to the model's actual dimension before "
                    "creating or migrating a collection.",
                )
            self._dimension = metadata_dimension

    @classmethod
    def from_settings(cls, settings) -> FastEmbedEmbeddingProvider:
        """Factory hook used by ``app.services.rag.get_embedding_service``."""
        cache_dir = getattr(settings, "embedding_cache_dir", "") or None
        return cls(
            model=getattr(settings, "embedding_model", ""),
            dimension=settings.embedding_dim,
            cache_dir=cache_dir,
        )

    @property
    def dimension(self) -> int:
        return self._dimension

    @classmethod
    def clear_model_cache(cls) -> None:
        """Drop cached models (tests / explicit cache reset)."""
        with _MODEL_CACHE_LOCK:
            _MODEL_CACHE.clear()

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        encoder = await asyncio.to_thread(self._ensure_encoder)
        try:
            raw = await asyncio.to_thread(self._embed_passages, encoder, texts)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001 - never leak model internals
            logger.exception("FastEmbed document embedding failed for %s", self.model_name)
            raise AppError(
                "SERVICE_UNAVAILABLE",
                "The embedding model could not encode the document text.",
            ) from exc
        return self._validate_vectors(raw, expected=len(texts))

    async def embed_query(self, text: str) -> list[float]:
        encoder = await asyncio.to_thread(self._ensure_encoder)
        try:
            raw = await asyncio.to_thread(self._embed_query_text, encoder, text)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001 - never leak model internals
            logger.exception("FastEmbed query embedding failed for %s", self.model_name)
            raise AppError(
                "SERVICE_UNAVAILABLE",
                "The embedding model could not encode the search query.",
            ) from exc
        return self._validate_vectors(raw, expected=1)[0]

    # -------------------------------------------------------------- internals
    def _ensure_encoder(self) -> Any:
        """Load the model once per configuration, off the event loop."""
        if self._encoder is not None:
            return self._encoder

        source = self._encoder_factory or self._encoder_cls
        if self._encoder_factory is not None or not _is_fastembed_text_embedding(source):
            self._encoder = self._build_encoder(source)
            return self._encoder

        key = (source, self.model_name, self.cache_dir)
        with _MODEL_CACHE_LOCK:
            cached = _MODEL_CACHE.get(key)
            if cached is not None:
                _MODEL_CACHE.move_to_end(key)
                self._encoder = cached
                return cached

            encoder = self._build_encoder(source)
            _MODEL_CACHE[key] = encoder
            _MODEL_CACHE.move_to_end(key)
            while len(_MODEL_CACHE) > _MAX_CACHED_MODELS:
                _MODEL_CACHE.popitem(last=False)
            self._encoder = encoder
            return encoder

    def _build_encoder(self, source: Any) -> Any:
        kwargs: dict[str, Any] = {"model_name": self.model_name}
        if self.cache_dir:
            kwargs["cache_dir"] = self.cache_dir
        try:
            return source(**kwargs)
        except ServiceNotConfiguredError:
            raise
        except ValueError as exc:
            # FastEmbed raises ValueError for unknown model names. That is a
            # configuration error; other value errors are load failures.
            message = str(exc).casefold()
            if "support" in message or "not found" in message:
                logger.warning(
                    "FastEmbed embedding model %s is unsupported", self.model_name
                )
                raise ServiceNotConfiguredError(
                    "SERVICE_NOT_CONFIGURED",
                    f"EMBEDDING_MODEL '{self.model_name}' is not supported by "
                    "FastEmbed. Check the model name and the FastEmbed cache.",
                ) from exc
            logger.exception(
                "FastEmbed embedding model %s could not be loaded", self.model_name
            )
            raise AppError(
                "SERVICE_UNAVAILABLE",
                f"The embedding model '{self.model_name}' could not be loaded. "
                "Check EMBEDDING_MODEL and the FastEmbed cache.",
            ) from exc
        except Exception as exc:  # noqa: BLE001 - never leak model internals
            logger.exception(
                "FastEmbed embedding model %s could not be loaded", self.model_name
            )
            raise AppError(
                "SERVICE_UNAVAILABLE",
                f"The embedding model '{self.model_name}' could not be loaded. "
                "Check EMBEDDING_MODEL and the FastEmbed cache.",
            ) from exc

    @staticmethod
    def _embed_passages(encoder: Any, texts: list[str]) -> Any:
        method = getattr(encoder, "passage_embed", None)
        if not callable(method):
            method = encoder.embed
        return method(texts)

    @staticmethod
    def _embed_query_text(encoder: Any, text: str) -> Any:
        method = getattr(encoder, "query_embed", None)
        if not callable(method):
            method = encoder.embed
        return method(text)

    def _validate_vectors(self, raw: Any, *, expected: int) -> list[list[float]]:
        """Check count, dimension and finiteness before vectors leave the provider."""
        vectors: list[list[float]] = []
        try:
            for vector in raw:
                values = [float(value) for value in vector]
                if len(values) != self._dimension:
                    raise AppError(
                        "SERVICE_UNAVAILABLE",
                        "The embedding model returned a vector with an unexpected dimension.",
                    )
                if any(not math.isfinite(value) for value in values):
                    raise AppError(
                        "SERVICE_UNAVAILABLE",
                        "The embedding model returned an invalid value.",
                    )
                vectors.append(values)
        except AppError:
            raise
        except Exception as exc:  # noqa: BLE001 - malformed provider output
            logger.exception("FastEmbed returned malformed vectors for %s", self.model_name)
            raise AppError(
                "SERVICE_UNAVAILABLE",
                "The embedding model returned malformed vectors.",
            ) from exc

        if len(vectors) != expected:
            logger.error(
                "FastEmbed returned %d vectors for %d inputs", len(vectors), expected
            )
            raise AppError(
                "SERVICE_UNAVAILABLE",
                "The embedding model returned an unexpected number of vectors.",
            )
        return vectors


__all__ = [
    "DEFAULT_FASTEMBED_DIMENSION",
    "DEFAULT_FASTEMBED_MODEL",
    "FASTEMBED_MIN_VERSION",
    "FASTEMBED_PROVIDER_NAME",
    "HASHING_PROVIDER_NAME",
    "EmbeddingService",
    "FastEmbedEmbeddingProvider",
    "HashingEmbeddingProvider",
    "fastembed_model_dimension",
]
