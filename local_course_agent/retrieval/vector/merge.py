from __future__ import annotations

from typing import Any, Dict, List, Mapping, Sequence

from local_course_agent.retrieval.vector.builders import chunk_id, chunk_text
from local_course_agent.retrieval.vector.math import numeric_score
from local_course_agent.retrieval.vector.schema import VectorSearchResult


def hybrid_merge_lexical_vector(
    lexical_hits: Sequence[Any],
    vector_hits: Sequence[Any],
    limit: int = 5,
) -> List[Dict]:
    if limit <= 0:
        return []

    fused: Dict[str, Dict] = {}
    rrf_k = 60

    for rank, raw_hit in enumerate(lexical_hits, start=1):
        hit = normalize_hit(raw_hit, source="lexical")
        key = hit_key(hit, rank)
        current = fused.setdefault(key, hit)
        if current is not hit:
            merge_missing_fields(current, hit)
        current["lexical_rank"] = rank
        current["lexical_score"] = numeric_score(hit.get("score"), hit.get("rrf_score"), hit.get("bm25_score"))
        current.setdefault("retrieval_sources", [])
        if "lexical" not in current["retrieval_sources"]:
            current["retrieval_sources"].append("lexical")
        current["hybrid_rrf_score"] = current.get("hybrid_rrf_score", 0.0) + 1 / (rrf_k + rank)

    for rank, raw_hit in enumerate(vector_hits, start=1):
        hit = normalize_hit(raw_hit, source="vector")
        key = hit_key(hit, rank)
        current = fused.setdefault(key, hit)
        if current is not hit:
            merge_missing_fields(current, hit)
        current["vector_rank"] = rank
        current["vector_score"] = numeric_score(hit.get("vector_score"), hit.get("score"))
        current.setdefault("retrieval_sources", [])
        if "vector" not in current["retrieval_sources"]:
            current["retrieval_sources"].append("vector")
        current["hybrid_rrf_score"] = current.get("hybrid_rrf_score", 0.0) + 1 / (rrf_k + rank)

    merged = list(fused.values())
    for hit in merged:
        hit["score"] = round(hit.get("hybrid_rrf_score", 0.0) * 1000, 4)
        hit["retrieval_method"] = merged_retrieval_method(hit)

    merged.sort(
        key=lambda hit: (
            hit.get("hybrid_rrf_score", 0.0),
            "lexical" in hit.get("retrieval_sources", []),
            hit.get("vector_score", float("-inf")),
            hit.get("lexical_score", float("-inf")),
        ),
        reverse=True,
    )
    return merged[:limit]


def normalize_hit(raw_hit: Any, source: str) -> Dict:
    if isinstance(raw_hit, Mapping):
        hit = dict(raw_hit)
    elif isinstance(raw_hit, VectorSearchResult):
        hit = dict(raw_hit.metadata)
        hit["id"] = raw_hit.id
        hit["text"] = raw_hit.text
        hit["vector_score"] = raw_hit.score
    else:
        metadata = dict(getattr(raw_hit, "metadata", {}) or {})
        hit = metadata
        if hasattr(raw_hit, "id"):
            hit["id"] = getattr(raw_hit, "id")
        if hasattr(raw_hit, "text"):
            hit["text"] = getattr(raw_hit, "text")
        if hasattr(raw_hit, "score"):
            score = getattr(raw_hit, "score")
            hit["vector_score" if source == "vector" else "score"] = score
    if source == "vector" and "vector_score" not in hit and "score" in hit:
        hit["vector_score"] = hit["score"]
    if "id" not in hit or not hit["id"]:
        hit["id"] = chunk_id(hit, 0)
    if "text" not in hit:
        hit["text"] = chunk_text(hit)
    return hit


def hit_key(hit: Mapping[str, Any], fallback_rank: int) -> str:
    if hit.get("id"):
        return str(hit["id"])
    if hit.get("file_id") is not None and hit.get("chunk_index") is not None:
        return f"{hit.get('file_id')}:{hit.get('page')}:{hit.get('chunk_index')}"
    if hit.get("file_name") is not None and hit.get("chunk_index") is not None:
        return f"{hit.get('file_name')}:{hit.get('page')}:{hit.get('chunk_index')}"
    return f"hit:{fallback_rank}"


def merge_missing_fields(target: Dict, source: Mapping[str, Any]) -> None:
    for key, value in source.items():
        if key not in target or target[key] in (None, "", []):
            target[key] = value


def merged_retrieval_method(hit: Mapping[str, Any]) -> str:
    sources = hit.get("retrieval_sources", [])
    if "lexical" in sources and "vector" in sources:
        return "hybrid_lexical_vector_rrf"
    if "vector" in sources:
        return "vector"
    return str(hit.get("retrieval_method") or "lexical")
