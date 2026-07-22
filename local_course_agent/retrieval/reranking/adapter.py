from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from local_course_agent.retrieval.reranking.documents import candidate_text
from local_course_agent.retrieval.reranking.fallback import LocalRerankFallback
from local_course_agent.retrieval.reranking.protocol import CandidateReranker


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
        return apply_provider_style_reranker(
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


def apply_provider_style_reranker(reranker: Any, *, query: str, documents: Sequence[Dict], top_n: int) -> List[Dict]:
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
