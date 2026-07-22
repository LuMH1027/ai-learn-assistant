from __future__ import annotations

from local_course_agent.retrieval.chunking import (
    material_type,
    split_structured_text,
    split_text,
    tokenize,
)
from local_course_agent.retrieval.rag.artifacts import (
    citation_from_chunk,
    generate_quiz_from_chunks,
    generate_summary_from_chunks,
    summarize_evidence,
)
from local_course_agent.retrieval.rag.indexing import append_text_chunks
from local_course_agent.retrieval.rag.store import (
    GENERATED_ARTIFACT_RE,
    INDEX_SCHEMA_VERSION,
    atomic_write_text,
)
from local_course_agent.retrieval.ranking import (
    compact_sentence,
    pick_keyword,
    retrieval_quality,
    retrieval_trace,
)
from local_course_agent.retrieval.reranking import CandidateReranker, LocalRerankFallback, apply_reranker
from local_course_agent.retrieval.vector_index import (
    VectorIndex,
    build_vector_index_from_chunks,
    create_embedding_model,
)


_summarize_evidence = summarize_evidence
_atomic_write_text = atomic_write_text


__all__ = [
    "GENERATED_ARTIFACT_RE",
    "INDEX_SCHEMA_VERSION",
    "CandidateReranker",
    "LocalRerankFallback",
    "VectorIndex",
    "_atomic_write_text",
    "_summarize_evidence",
    "append_text_chunks",
    "apply_reranker",
    "atomic_write_text",
    "build_vector_index_from_chunks",
    "citation_from_chunk",
    "compact_sentence",
    "create_embedding_model",
    "material_type",
    "pick_keyword",
    "retrieval_quality",
    "retrieval_trace",
    "split_structured_text",
    "split_text",
    "summarize_evidence",
    "tokenize",
]
