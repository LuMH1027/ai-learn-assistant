from __future__ import annotations

from typing import Any, Dict, List, Mapping, Protocol, Sequence, runtime_checkable

from local_course_agent.retrieval.reranking.documents import candidate_text
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


@runtime_checkable
class CandidateReranker(Protocol):
    """Optional cross-encoder reranker hook for RAG candidates.

    Providers such as SiliconFlow can either implement this hook directly or
    expose the provider-style ``rerank(query, documents, top_n)`` method. The
    adapter below maps candidate dicts to text documents for that provider
    shape and merges returned ``index``/``score`` values back into candidates.
    """

    def rerank(self, *, query: str, documents: Sequence[Dict], top_n: int, stage: str) -> Sequence[Dict]:
        ...


class LocalRerankFallback:
    """No-op reranker because local scores are already attached upstream."""

    def rerank(self, *, query: str, documents: Sequence[Dict], top_n: int, stage: str) -> Sequence[Dict]:
        return list(documents)[:top_n]


def apply_reranker(
    reranker: CandidateReranker | None,
    *,
    query: str,
    documents: Sequence[Dict],
    top_n: int,
    stage: str,
) -> List[Dict]:
    if top_n <= 0:
        return []
    active_reranker = reranker or LocalRerankFallback()
    try:
        ranked = active_reranker.rerank(
            query=query,
            documents=list(documents),
            top_n=top_n,
            stage=stage,
        )
    except TypeError:
        return _apply_provider_style_reranker(
            active_reranker,
            query=query,
            documents=documents,
            top_n=top_n,
        )
    except Exception:
        return list(documents)[:top_n]
    normalized = [_normalize_reranked_item(item, documents) for item in ranked]
    ranked_documents = [item for item in normalized if item is not None][:top_n]
    return ranked_documents or list(documents)[:top_n]


def _normalize_reranked_item(item, source_documents: Sequence[Dict]) -> Dict | None:
    if isinstance(item, dict):
        document = item.get("document")
        if isinstance(document, dict):
            merged = dict(document)
            if "score" in item:
                merged["external_rerank_score"] = item["score"]
            if "rerank_score" in item:
                merged["external_rerank_score"] = item["rerank_score"]
            return merged
        return dict(item)
    if isinstance(item, int) and 0 <= item < len(source_documents):
        return dict(source_documents[item])
    return None


def _apply_provider_style_reranker(reranker: Any, *, query: str, documents: Sequence[Dict], top_n: int) -> List[Dict]:
    try:
        results = reranker.rerank(query, [candidate_text(document) for document in documents], top_n=top_n)
    except Exception:
        return list(documents)[:top_n]
    by_index = []
    for result in results or []:
        if not isinstance(result, Mapping):
            continue
        raw_index = result.get("index")
        raw_score = result.get("score", result.get("relevance_score"))
        if raw_index is None:
            continue
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            continue
        if not 0 <= index < len(documents):
            continue
        item = dict(documents[index])
        if raw_score is not None:
            item["external_rerank_score"] = float(raw_score)
            item["local_rerank_score"] = float(raw_score)
        item["rerank_model"] = getattr(reranker, "model_id", "")
        by_index.append(item)
    return by_index[:top_n] or list(documents)[:top_n]


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
