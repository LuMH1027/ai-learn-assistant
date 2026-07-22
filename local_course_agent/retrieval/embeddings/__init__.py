from __future__ import annotations

from local_course_agent.retrieval.embeddings.config import config_float, config_int, create_embedding_model, optional_int
from local_course_agent.retrieval.embeddings.models import (
    EmbeddingModel,
    EmbeddingRequestError,
    VectorIndexCompatibilityError,
    default_model_for_saved_index,
    embedding_model_metadata,
    validate_saved_model_compatibility,
)
from local_course_agent.retrieval.embeddings.openai_client import OpenAIEmbeddingHTTPClient
from local_course_agent.retrieval.embeddings.openai_payloads import (
    build_embedding_payload,
    parse_embedding_response,
)
from local_course_agent.retrieval.embeddings.providers import FakeEmbeddingModel, OpenAICompatibleEmbeddingModel
from local_course_agent.retrieval.embeddings.utils import (
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
    "OpenAIEmbeddingHTTPClient",
    "OpenAICompatibleEmbeddingModel",
    "VectorIndexCompatibilityError",
    "build_embedding_payload",
    "config_float",
    "config_int",
    "create_embedding_model",
    "default_model_for_saved_index",
    "embedding_model_metadata",
    "http_error_detail",
    "model_fingerprint",
    "optional_int",
    "parse_embedding_response",
    "retryable_http_status",
    "sanitize_error_snippet",
    "tokens",
    "unit_vector",
    "validate_saved_model_compatibility",
]
