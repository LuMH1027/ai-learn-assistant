from __future__ import annotations

from local_course_agent.retrieval.reranking.adapter import (
    apply_provider_style_reranker,
    apply_provider_style_reranker as _apply_provider_style_reranker,
    apply_reranker,
)
from local_course_agent.retrieval.reranking.documents import candidate_text
from local_course_agent.retrieval.reranking.fallback import LocalRerankFallback
from local_course_agent.retrieval.reranking.protocol import CandidateReranker
from local_course_agent.retrieval.reranking.providers import (
    DEFAULT_RERANK_TIMEOUT,
    DEFAULT_RERANK_TOP_N,
    NoopReranker,
    RerankRequestError,
    Reranker,
    SiliconFlowReranker,
    apply_external_rerank,
    create_reranker,
    parse_rerank_results,
)


__all__ = [
    "CandidateReranker",
    "LocalRerankFallback",
    "apply_reranker",
    "candidate_text",
    "DEFAULT_RERANK_TIMEOUT",
    "DEFAULT_RERANK_TOP_N",
    "NoopReranker",
    "RerankRequestError",
    "Reranker",
    "SiliconFlowReranker",
    "apply_external_rerank",
    "create_reranker",
    "parse_rerank_results",
]
