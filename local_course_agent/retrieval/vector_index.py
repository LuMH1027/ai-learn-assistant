from __future__ import annotations

from local_course_agent.retrieval.embeddings import (
    DEFAULT_DIMENSIONS,
    EmbeddingModel,
    EmbeddingRequestError,
    FakeEmbeddingModel,
    OpenAICompatibleEmbeddingModel,
    VectorIndexCompatibilityError,
    create_embedding_model,
    default_model_for_saved_index,
    embedding_model_metadata,
    validate_saved_model_compatibility,
)
from local_course_agent.retrieval.vector import (
    SCHEMA_VERSION,
    VectorDocument,
    VectorIndex,
    VectorSearchResult,
    build_vector_index_from_chunks,
    cosine_similarity,
    hybrid_merge_lexical_vector,
)
from local_course_agent.retrieval.vector.builders import chunk_id as _chunk_id
from local_course_agent.retrieval.vector.builders import chunk_text as _chunk_text
from local_course_agent.retrieval.vector.math import numeric_score as _numeric_score
from local_course_agent.retrieval.vector.merge import (
    hit_key as _hit_key,
    merge_missing_fields as _merge_missing_fields,
    merged_retrieval_method as _merged_retrieval_method,
    normalize_hit as _normalize_hit,
)
from local_course_agent.retrieval.vector.persistence import atomic_write_text as _atomic_write_text


__all__ = [
    "DEFAULT_DIMENSIONS",
    "SCHEMA_VERSION",
    "EmbeddingModel",
    "EmbeddingRequestError",
    "FakeEmbeddingModel",
    "OpenAICompatibleEmbeddingModel",
    "VectorDocument",
    "VectorIndex",
    "VectorIndexCompatibilityError",
    "VectorSearchResult",
    "build_vector_index_from_chunks",
    "cosine_similarity",
    "create_embedding_model",
    "default_model_for_saved_index",
    "embedding_model_metadata",
    "hybrid_merge_lexical_vector",
    "validate_saved_model_compatibility",
]
