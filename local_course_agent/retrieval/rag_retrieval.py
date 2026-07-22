from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence

from local_course_agent.retrieval.chunking import material_type, tokenize
from local_course_agent.retrieval.ranking import (
    expand_query_tokens,
    indexable_chunk_text,
    neighbor_context,
    normalize_query,
    rank_candidates,
    select_diverse,
    select_hybrid_vector_hits,
)
from local_course_agent.retrieval.reranking import CandidateReranker, apply_reranker
from local_course_agent.retrieval.vector_index import VectorIndex


VectorIndexLoader = Callable[[str, Sequence[Dict]], Optional[VectorIndex]]


def search_course_chunks(
    *,
    course_id: str,
    chunks: List[Dict],
    query: str,
    limit: int = 5,
    strategy: str = "lexical",
    vector_index_loader: VectorIndexLoader | None = None,
    reranker: CandidateReranker | None = None,
) -> List[Dict]:
    normalized_query = normalize_query(query)
    original_query_tokens = [
        token
        for token in tokenize(normalized_query)
        if not (token.isdigit() and len(token) < 4)
    ]
    query_tokens = expand_query_tokens(normalized_query, original_query_tokens) if strategy == "hybrid" else original_query_tokens
    if not query_tokens:
        return []

    prepare_search_chunks(chunks)
    if not chunks:
        return []

    candidates = rank_candidates(chunks, normalized_query, query_tokens, limit)
    candidates = apply_reranker(
        reranker,
        query=normalized_query,
        documents=candidates,
        top_n=max(limit * 6, 18),
        stage="pre_hybrid_selection",
    )
    selected = select_candidates(
        course_id=course_id,
        chunks=chunks,
        candidates=candidates,
        normalized_query=normalized_query,
        limit=limit,
        strategy=strategy,
        vector_index_loader=vector_index_loader,
    )
    selected = apply_reranker(
        reranker,
        query=normalized_query,
        documents=selected,
        top_n=limit,
        stage="post_hybrid_selection",
    )
    return enrich_selected_hits(selected, chunks, original_query_tokens, strategy)


def prepare_search_chunks(chunks: Sequence[Dict]) -> None:
    for chunk in chunks:
        # Existing indexes are upgraded lazily after tokenizer changes.
        chunk["section_title"] = chunk.get("section_title", "")
        chunk["material_type"] = chunk.get("material_type") or material_type(chunk.get("file_name", ""), chunk.get("file_path", ""))
        chunk["tokens"] = tokenize(indexable_chunk_text(chunk))


def select_candidates(
    *,
    course_id: str,
    chunks: Sequence[Dict],
    candidates: Sequence[Dict],
    normalized_query: str,
    limit: int,
    strategy: str,
    vector_index_loader: VectorIndexLoader | None,
) -> List[Dict]:
    if strategy != "hybrid":
        return select_diverse(candidates, limit)
    vector_index = vector_index_loader(course_id, chunks) if vector_index_loader else None
    return select_hybrid_vector_hits(
        chunks,
        candidates,
        normalized_query,
        limit,
        vector_index=vector_index,
    )


def enrich_selected_hits(
    selected: Sequence[Dict],
    chunks: Sequence[Dict],
    original_query_tokens: Sequence[str],
    strategy: str,
) -> List[Dict]:
    enriched = list(selected)
    for item in enriched:
        item["context_text"] = neighbor_context(item, chunks)
        if "hybrid_rrf_score" in item:
            item["score"] = round(item["hybrid_rrf_score"] * 1000, 4)
            item["retrieval_method"] = item.get("retrieval_method") or "hybrid_lexical_vector_rrf"
        else:
            item["score"] = round(item["rrf_score"] * 1000, 4)
            item["retrieval_method"] = "hybrid_bm25_semantic_rrf_mmr" if strategy == "hybrid" else "bm25_rrf_mmr"
        query_set = set(original_query_tokens)
        item["query_coverage"] = round(
            len(query_set & set(item.get("tokens", []))) / max(len(query_set), 1),
            4,
        )
        item["matched_terms"] = sorted(set(original_query_tokens) & set(item.get("tokens", [])))[:12]
    return enriched
