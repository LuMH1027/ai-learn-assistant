from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List, Sequence

from local_course_agent.retrieval.chunking import tokenize
from local_course_agent.retrieval.vector_index import (
    VectorIndex,
    hybrid_merge_lexical_vector,
)


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
