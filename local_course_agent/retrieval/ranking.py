from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Sequence

from local_course_agent.retrieval.chunking import TOKEN_RE, tokenize
from local_course_agent.retrieval.vector_index import (
    VectorIndex,
    hybrid_merge_lexical_vector,
)


QUERY_STOP_TOKENS = {
    "什么",
    "怎么",
    "如何",
    "为什么",
    "哪些",
    "是否",
    "请问",
    "一下",
    "作用",
    "主要",
    "含义",
    "介绍",
    "说明",
}
QUERY_EXPANSIONS = {
    "地址转换": ["页表", "tlb", "虚拟地址", "物理地址"],
    "缺页": ["缺页中断", "页面置换", "调页"],
    "调度": ["进程", "线程", "cpu"],
    "后进先出": ["栈", "lifo"],
    "先进先出": ["队列", "fifo"],
    "映射": ["地址转换", "页表"],
    "缓存": ["tlb", "高速缓存"],
    "后备缓冲": ["tlb", "缓存"],
}


def normalize_query(query: str) -> str:
    normalized = query.lower()
    for stopword in sorted(QUERY_STOP_TOKENS, key=len, reverse=True):
        normalized = normalized.replace(stopword, " ")
    return normalized


def expand_query_tokens(query: str, tokens: Sequence[str]) -> List[str]:
    expanded = list(tokens)
    query_text = query.lower()
    for trigger, additions in QUERY_EXPANSIONS.items():
        trigger_tokens = tokenize(trigger)
        if trigger in query_text or any(token in tokens for token in trigger_tokens):
            expanded.extend(token for addition in additions for token in tokenize(addition))
    return expanded


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


def query_phrases(query: str) -> List[str]:
    phrases = []
    for phrase in TOKEN_RE.findall(query.lower()):
        if phrase in QUERY_STOP_TOKENS:
            continue
        if re.fullmatch(r"[\u4e00-\u9fff]+", phrase):
            cleaned = phrase
            for stopword in QUERY_STOP_TOKENS:
                cleaned = cleaned.replace(stopword, " ")
            phrases.extend(part for part in cleaned.split() if len(part) >= 2)
        elif len(phrase) >= 2:
            phrases.append(phrase)
    return phrases


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


def semantic_features(text: str) -> set[str]:
    features = set()
    for token in tokenize(text):
        if len(token) >= 2 and token not in QUERY_STOP_TOKENS:
            features.add(token)
    compact = re.sub(r"\s+", "", text.lower())
    features.update(compact[index : index + 4] for index in range(max(0, len(compact) - 3)))
    return features


def reciprocal_rank_fusion(rankings: Sequence[Sequence[Dict]], candidate_limit: int, k: int = 60) -> List[Dict]:
    fused: Dict[str, Dict] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking[:candidate_limit], start=1):
            key = item["id"]
            if key not in fused:
                fused[key] = dict(item)
                fused[key]["rrf_score"] = 0.0
            fused[key]["rrf_score"] += 1 / (k + rank)
    return sorted(fused.values(), key=lambda item: item["rrf_score"], reverse=True)[:candidate_limit]


def select_hybrid_vector_hits(
    chunks: Sequence[Dict],
    lexical_candidates: Sequence[Dict],
    query: str,
    limit: int,
    vector_index: VectorIndex | None = None,
) -> List[Dict]:
    lexical_selected = select_diverse(lexical_candidates, max(limit * 2, limit))
    if vector_index is None:
        return select_diverse(lexical_candidates, limit)
    try:
        vector_hits = vector_index.search(
            query,
            limit=max(limit * 4, 12),
            min_score=0.2,
        )
    except Exception:
        return select_diverse(lexical_candidates, limit)

    if not vector_hits:
        return select_diverse(lexical_candidates, limit)

    merged = hybrid_merge_lexical_vector(
        lexical_selected,
        vector_hits,
        limit=max(limit * 4, 12),
    )
    for hit in merged:
        hit["rrf_score"] = hit.get("hybrid_rrf_score", hit.get("rrf_score", 0.0))
        if "local_rerank_score" not in hit:
            hit["local_rerank_score"] = min(max(float(hit.get("vector_score", 0.0)), 0.0), 1.0)
    return select_diverse(merged, limit)


def select_diverse(candidates: Sequence[Dict], limit: int) -> List[Dict]:
    selected: List[Dict] = []
    remaining = list(candidates)
    max_score = max((item["rrf_score"] for item in remaining), default=1)
    while remaining and len(selected) < limit:

        def utility(item: Dict) -> float:
            relevance = item["rrf_score"] / max_score
            rerank = item.get("local_rerank_score", 0)
            redundancy = max((token_similarity(item, chosen) for chosen in selected), default=0)
            source_bonus = 0.12 if selected and all(item["file_id"] != chosen["file_id"] for chosen in selected) else 0
            return 0.56 * relevance + 0.28 * rerank - 0.22 * redundancy + source_bonus

        best = max(remaining, key=utility)
        selected.append(best)
        remaining.remove(best)
    return selected


def token_similarity(left: Dict, right: Dict) -> float:
    left_tokens = set(left.get("tokens", []))
    right_tokens = set(right.get("tokens", []))
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union) if union else 0


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


def neighbor_context(item: Dict, chunks: Sequence[Dict]) -> str:
    position = next((index for index, chunk in enumerate(chunks) if chunk.get("id") == item.get("id")), None)
    if position is None:
        return item["text"]
    related = []
    for index in range(max(0, position - 1), min(len(chunks), position + 2)):
        chunk = chunks[index]
        if chunk.get("file_id") == item.get("file_id") and chunk.get("page") == item.get("page"):
            related.append(chunk["text"])
    return "\n".join(related)


def representative_chunks(chunks: Sequence[Dict], limit: int) -> List[Dict]:
    ranked = sorted(
        chunks,
        key=lambda chunk: (
            len(set(token for token in chunk.get("tokens", []) if len(token) > 1)),
            len(chunk.get("text", "")),
        ),
        reverse=True,
    )
    selected: List[Dict] = []
    used_files = set()
    used_keywords = set()
    for chunk in ranked:
        keyword = pick_keyword(chunk.get("text", ""))
        if len(selected) < limit and (chunk.get("file_id") not in used_files or keyword not in used_keywords):
            selected.append(chunk)
            used_files.add(chunk.get("file_id"))
            used_keywords.add(keyword)
        if len(selected) >= limit:
            break
    for chunk in ranked:
        if len(selected) >= limit:
            break
        if chunk not in selected:
            selected.append(chunk)
    return selected


def compact_sentence(text: str, limit: int = 150) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= limit:
        return clean
    boundary = max(clean.rfind("。", 0, limit), clean.rfind("；", 0, limit), clean.rfind(".", 0, limit))
    if boundary >= 40:
        return clean[: boundary + 1]
    return clean[:limit].rstrip() + "..."


def pick_keyword(text: str) -> str:
    preferred_terms = [
        "虚拟内存",
        "文件系统",
        "二叉搜索树",
        "平衡二叉树",
        "循环队列",
        "进程",
        "线程",
        "页表",
        "队列",
        "栈",
        "二叉树",
    ]
    for term in preferred_terms:
        if term in text:
            return term
    chinese_terms = re.findall(r"[\u4e00-\u9fff]{2,8}", text)
    stop_terms = {"本课程", "示例资料", "本地课程", "参考要点"}
    for term in chinese_terms:
        if term not in stop_terms:
            return term
    tokens = [token for token in tokenize(text) if len(token) > 1]
    if not tokens:
        return "核心概念"
    counter = Counter(tokens)
    return counter.most_common(1)[0][0]


def indexable_chunk_text(chunk: Dict) -> str:
    parts = [
        chunk.get("file_name", ""),
        chunk.get("file_path", ""),
        chunk.get("section_title", ""),
        chunk.get("text", ""),
    ]
    return "\n".join(part for part in parts if part)
