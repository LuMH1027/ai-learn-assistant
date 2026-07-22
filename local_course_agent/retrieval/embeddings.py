from __future__ import annotations

from local_course_agent.retrieval.embedding_config import config_float, config_int, create_embedding_model, optional_int
from local_course_agent.retrieval.embedding_models import (
    EmbeddingModel,
    EmbeddingRequestError,
    VectorIndexCompatibilityError,
    default_model_for_saved_index,
    embedding_model_metadata,
    validate_saved_model_compatibility,
)
from local_course_agent.retrieval.embedding_providers import FakeEmbeddingModel, OpenAICompatibleEmbeddingModel
from local_course_agent.retrieval.embedding_utils import (
    DEFAULT_DIMENSIONS,
    DEFAULT_EMBEDDING_BATCH_SIZE,
    DEFAULT_EMBEDDING_MAX_RETRIES,
    DEFAULT_EMBEDDING_RETRY_DELAY,
    _tokens,
    http_error_detail,
    model_fingerprint,
    retryable_http_status,
    sanitize_error_snippet,
    tokens,
    unit_vector,
)


__all__ = [
    "DEFAULT_DIMENSIONS",
    "DEFAULT_EMBEDDING_BATCH_SIZE",
    "DEFAULT_EMBEDDING_MAX_RETRIES",
    "DEFAULT_EMBEDDING_RETRY_DELAY",
    "EmbeddingModel",
    "EmbeddingRequestError",
    "FakeEmbeddingModel",
    "OpenAICompatibleEmbeddingModel",
    "VectorIndexCompatibilityError",
    "config_float",
    "config_int",
    "create_embedding_model",
    "default_model_for_saved_index",
    "embedding_model_metadata",
    "http_error_detail",
    "model_fingerprint",
    "optional_int",
    "retryable_http_status",
    "sanitize_error_snippet",
    "tokens",
    "unit_vector",
    "validate_saved_model_compatibility",
]
