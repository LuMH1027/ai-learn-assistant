from __future__ import annotations

import math
from collections import Counter
from typing import Dict, List, Sequence

from local_course_agent.retrieval.chunking import tokenize
from local_course_agent.retrieval.query import (
    indexable_chunk_text,
    query_phrases,
    semantic_features,
)
from local_course_agent.retrieval.selection import reciprocal_rank_fusion


def rank_candidates(chunks: Sequence[Dict], query: str, query_tokens: Sequence[str], limit: int) -> List[Dict]:
    query_counter = Counter(query_tokens)
    bm25_ranking = bm25_rank(chunks, query_counter)
    phrases = query_phrases(query)
    phrase_ranking = sorted(
        (dict(chunk) for chunk in chunks if phrase_score(chunk, phrases) > 0),
        key=lambda chunk: phrase_score(chunk, phrases),
        reverse=True,
    )
    metadata_ranking = sorted(
        (dict(chunk) for chunk in chunks if metadata_score(chunk, query_tokens) > 0),
        key=lambda chunk: metadata_score(chunk, query_tokens),
        reverse=True,
    )
    semantic_ranking = sorted(
        (dict(chunk) for chunk in chunks if semantic_score(query, query_tokens, chunk) > 0),
        key=lambda chunk: semantic_score(query, query_tokens, chunk),
        reverse=True,
    )

    candidates = reciprocal_rank_fusion(
        [bm25_ranking, phrase_ranking, metadata_ranking, semantic_ranking],
        candidate_limit=max(limit * 6, 18),
    )
    for candidate in candidates:
        candidate["local_rerank_score"] = local_rerank_score(
            candidate,
            query_tokens=query_tokens,
            phrases=phrases,
            normalized_query=query,
        )
    candidates.sort(key=lambda item: (item.get("local_rerank_score", 0), item.get("rrf_score", 0)), reverse=True)
    return candidates


def bm25_rank(chunks: Sequence[Dict], query_counter: Counter) -> List[Dict]:
    total_docs = max(len(chunks), 1)
    average_length = sum(len(chunk["tokens"]) for chunk in chunks) / total_docs
    document_frequency = Counter()
    for chunk in chunks:
        document_frequency.update(set(chunk["tokens"]))

    bm25_ranking = []
    k1 = 1.5
    b = 0.75
    for chunk in chunks:
        chunk_counter = Counter(chunk["tokens"])
        score = 0.0
        for token, query_weight in query_counter.items():
            term_frequency = chunk_counter[token]
            if not term_frequency:
                continue
            idf = math.log(1 + (total_docs - document_frequency[token] + 0.5) / (document_frequency[token] + 0.5))
            length_norm = term_frequency + k1 * (
                1 - b + b * len(chunk["tokens"]) / max(average_length, 1)
            )
            score += query_weight * idf * (term_frequency * (k1 + 1) / length_norm)
        if score > 0:
            item = dict(chunk)
            item["bm25_score"] = score
            bm25_ranking.append(item)
    bm25_ranking.sort(key=lambda item: item["bm25_score"], reverse=True)
    return bm25_ranking


def phrase_score(chunk: Dict, phrases: Sequence[str]) -> float:
    text = indexable_chunk_text(chunk).lower()
    return sum(len(phrase) * text.count(phrase) for phrase in phrases)


def metadata_score(chunk: Dict, query_tokens: Sequence[str]) -> float:
    metadata_tokens = Counter(
        tokenize(
            " ".join(
                [
                    chunk.get("file_name", ""),
                    chunk.get("file_path", ""),
                    chunk.get("section_title", ""),
                    chunk.get("material_type", ""),
                ]
            )
        )
    )
    return sum(metadata_tokens[token] for token in set(query_tokens))


def semantic_score(query: str, query_tokens: Sequence[str], chunk: Dict) -> float:
    text = indexable_chunk_text(chunk).lower()
    aliases = {
        "后进先出": ("栈", "lifo"),
        "先进先出": ("队列", "fifo"),
        "地址变换": ("地址转换", "页表", "tlb"),
        "虚实地址": ("虚拟地址", "物理地址", "页表"),
        "缓存页表": ("tlb", "页表"),
        "递归调用": ("栈", "函数调用"),
        "广搜": ("队列", "广度优先搜索", "bfs"),
        "宽搜": ("队列", "广度优先搜索", "bfs"),
    }
    score = 0.0
    for trigger, related_terms in aliases.items():
        if trigger in query or any(token in query_tokens for token in tokenize(trigger)):
            score += sum(1.0 for term in related_terms if term.lower() in text)
    query_features = semantic_features(query)
    chunk_features = semantic_features(text)
    if query_features and chunk_features:
        overlap = query_features & chunk_features
        score += len(overlap) / ((len(query_features) * len(chunk_features)) ** 0.5)
    return score


def local_rerank_score(
    chunk: Dict,
    query_tokens: Sequence[str],
    phrases: Sequence[str],
    normalized_query: str,
) -> float:
    token_set = set(query_tokens)
    chunk_tokens = set(chunk.get("tokens", []))
    coverage = len(token_set & chunk_tokens) / max(len(token_set), 1)
    phrase = min(phrase_score(chunk, phrases) / 20, 1.0)
    metadata = min(metadata_score(chunk, query_tokens) / 3, 1.0)
    semantic = min(semantic_score(normalized_query, query_tokens, chunk), 1.0)
    title_hit = 0.12 if token_set & set(tokenize(chunk.get("section_title", ""))) else 0.0
    type_bonus = 0.06 if chunk.get("material_type") in {"textbook", "slides"} else 0.0
    return round(0.42 * coverage + 0.22 * phrase + 0.16 * semantic + 0.12 * metadata + title_hit + type_bonus, 4)


def retrieval_quality(max_coverage: float, max_score: float, hit_count: int) -> str:
    if hit_count == 0:
        return "none"
    if max_coverage >= 0.33 or (max_coverage >= 0.24 and max_score >= 45):
        return "sufficient"
    return "partial"


def retrieval_trace(hits: Sequence[Dict]) -> Dict:
    return {
        "selected": [
            {
                "file_name": hit.get("file_name", ""),
                "section_title": hit.get("section_title", ""),
                "material_type": hit.get("material_type", ""),
                "score": hit.get("score", 0),
                "query_coverage": hit.get("query_coverage", 0),
                "matched_terms": hit.get("matched_terms", []),
                "retrieval_method": hit.get("retrieval_method", ""),
            }
            for hit in hits
        ]
    }
