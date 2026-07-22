from __future__ import annotations

from local_course_agent.retrieval.vector.builders import build_vector_index_from_chunks
from local_course_agent.retrieval.vector.index import VectorIndex
from local_course_agent.retrieval.vector.math import cosine_similarity
from local_course_agent.retrieval.vector.merge import hybrid_merge_lexical_vector
from local_course_agent.retrieval.vector.schema import SCHEMA_VERSION, VectorDocument, VectorSearchResult


__all__ = [
    "SCHEMA_VERSION",
    "VectorDocument",
    "VectorIndex",
    "VectorSearchResult",
    "build_vector_index_from_chunks",
    "cosine_similarity",
    "hybrid_merge_lexical_vector",
]
