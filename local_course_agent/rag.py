from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Sequence


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")
GENERATED_ARTIFACT_RE = re.compile(r"^(?:课程摘要|练习题)-\d{8}-\d{6}\.md$", re.IGNORECASE)
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


def tokenize(text: str) -> List[str]:
    tokens: List[str] = []
    for raw in TOKEN_RE.findall(text):
        token = raw.lower()
        if not re.fullmatch(r"[\u4e00-\u9fff]+", token):
            tokens.append(token)
            continue
        if len(token) <= 8:
            tokens.append(token)
        if len(token) == 1:
            tokens.append(token)
            continue
        for width in (2, 3):
            tokens.extend(token[index : index + width] for index in range(len(token) - width + 1))
    return tokens


def split_text(text: str, chunk_size: int = 520, overlap: int = 80) -> List[str]:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []
    chunks = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + chunk_size)
        chunks.append(clean[start:end])
        if end == len(clean):
            break
        start = max(end - overlap, start + 1)
    return chunks


class CourseKnowledgeBase:
    """A lightweight local RAG store with per-course isolation.

    It intentionally uses JSON files and lexical scoring so the project can run
    on a fresh Windows machine before optional vector-search upgrades.
    """

    def __init__(self, storage_dir: Path):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def index_text(self, course_id: str, file_id: str, file_name: str, text: str, page=None) -> int:
        chunks = self._material_chunks(course_id)
        chunks = [chunk for chunk in chunks if not (chunk["file_id"] == file_id and chunk.get("page") == page)]
        next_index = len(chunks) + 1
        next_index = self._append_text_chunks(
            chunks,
            course_id=course_id,
            file_id=file_id,
            file_name=file_name,
            text=text,
            page=page,
            next_index=next_index,
        )
        self._save(course_id, chunks)
        return len(chunks)

    def rebuild_course(self, course_id: str, documents: Sequence[Dict]) -> int:
        chunks: List[Dict] = []
        next_index = 1
        for document in documents:
            for page in document.get("pages", []):
                next_index = self._append_text_chunks(
                    chunks,
                    course_id=course_id,
                    file_id=document["file_id"],
                    file_name=document["file_name"],
                    text=page.get("text", ""),
                    page=page.get("page"),
                    next_index=next_index,
                )
        self._save(course_id, chunks)
        return len(chunks)

    def clear_course(self, course_id: str) -> None:
        self._path(course_id).write_text("[]", encoding="utf-8")

    def search(self, course_id: str, query: str, limit: int = 5, strategy: str = "lexical") -> List[Dict]:
        normalized_query = _normalize_query(query)
        original_query_tokens = [
            token
            for token in tokenize(normalized_query)
            if not (token.isdigit() and len(token) < 4)
        ]
        query_tokens = _expand_query_tokens(normalized_query, original_query_tokens) if strategy == "hybrid" else original_query_tokens
        if not query_tokens:
            return []
        query_counter = Counter(query_tokens)
        chunks = self._material_chunks(course_id)
        for chunk in chunks:
            # Existing indexes are upgraded lazily after tokenizer changes.
            chunk["tokens"] = tokenize(chunk.get("text", ""))
        if not chunks:
            return []
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

        phrases = _query_phrases(normalized_query)
        phrase_ranking = sorted(
            (dict(chunk) for chunk in chunks if _phrase_score(chunk, phrases) > 0),
            key=lambda chunk: _phrase_score(chunk, phrases),
            reverse=True,
        )
        metadata_ranking = sorted(
            (dict(chunk) for chunk in chunks if _metadata_score(chunk, query_tokens) > 0),
            key=lambda chunk: _metadata_score(chunk, query_tokens),
            reverse=True,
        )
        semantic_ranking = sorted(
            (dict(chunk) for chunk in chunks if _semantic_score(normalized_query, query_tokens, chunk) > 0),
            key=lambda chunk: _semantic_score(normalized_query, query_tokens, chunk),
            reverse=True,
        )

        candidates = _reciprocal_rank_fusion(
            [bm25_ranking, phrase_ranking, metadata_ranking, semantic_ranking],
            candidate_limit=max(limit * 6, 18),
        )
        selected = _select_diverse(candidates, limit)
        for item in selected:
            item["context_text"] = _neighbor_context(item, chunks)
            item["score"] = round(item["rrf_score"] * 1000, 4)
            item["retrieval_method"] = "hybrid_bm25_semantic_rrf_mmr" if strategy == "hybrid" else "bm25_rrf_mmr"
            query_set = set(original_query_tokens)
            item["query_coverage"] = round(
                len(query_set & set(item.get("tokens", []))) / max(len(query_set), 1),
                4,
            )
        return selected

    def answer(self, course_id: str, query: str, strategy: str = "hybrid") -> Dict:
        hits = self.search(course_id, query, limit=4, strategy=strategy)
        if not hits:
            return {
                "answer": "未在当前课程资料中找到可靠依据。建议先确认该课程资料是否已完成入库，或换一种更贴近资料原文的提问方式。",
                "citations": [],
                "mode": "no_basis",
                "retrieval_quality": "none",
            }

        citations = [
            citation_from_chunk(hit)
            for hit in hits
        ]
        evidence = "\n".join(f"{idx}. {hit['context_text']}" for idx, hit in enumerate(hits, start=1))
        answer = (
            "基于当前课程资料，可以这样理解：\n"
            f"{_summarize_evidence(query, hits)}\n\n"
            "依据片段：\n"
            f"{evidence}"
        )
        max_coverage = max((hit.get("query_coverage", 0) for hit in hits), default=0)
        quality = "sufficient" if max_coverage >= 0.25 else "partial"
        return {
            "answer": answer,
            "citations": citations,
            "mode": "grounded",
            "retrieval_quality": quality,
        }

    def generate_summary(self, course_id: str, limit: int = 6) -> Dict:
        chunks = self._material_chunks(course_id)[:limit]
        if not chunks:
            return {"content": "当前课程还没有可用于生成摘要的资料片段，请先构建知识库。", "citations": []}
        citations = [citation_from_chunk(chunk) for chunk in chunks]
        points = []
        for chunk in chunks:
            text = chunk["text"]
            if len(text) > 120:
                text = text[:120] + "..."
            points.append(f"- 《{chunk['file_name']}》：{text}")
        return {
            "content": "课程复习摘要\n\n" + "\n".join(points),
            "citations": citations,
        }

    def generate_quiz(self, course_id: str, count: int = 5) -> Dict:
        chunks = self._material_chunks(course_id)[:count]
        if not chunks:
            return {"content": "当前课程还没有可用于生成练习题的资料片段，请先构建知识库。", "citations": []}
        questions = []
        for index, chunk in enumerate(chunks, start=1):
            keyword = _pick_keyword(chunk["text"])
            questions.append(
                f"{index}. 自测题：请结合《{chunk['file_name']}》说明“{keyword}”的含义或作用。\n"
                f"   参考要点：{chunk['text'][:120]}"
            )
        return {
            "content": "课程自测题\n\n" + "\n\n".join(questions),
            "citations": [citation_from_chunk(chunk) for chunk in chunks],
        }

    def _path(self, course_id: str) -> Path:
        return self.storage_dir / f"{course_id}.json"

    def _load(self, course_id: str) -> List[Dict]:
        path = self._path(course_id)
        if not path.exists():
            return []
        return json.loads(path.read_text(encoding="utf-8"))

    def _save(self, course_id: str, chunks: List[Dict]) -> None:
        self._path(course_id).write_text(json.dumps(chunks, ensure_ascii=False, indent=2), encoding="utf-8")

    def _append_text_chunks(
        self,
        chunks: List[Dict],
        course_id: str,
        file_id: str,
        file_name: str,
        text: str,
        page=None,
        next_index: int = 1,
    ) -> int:
        for text_chunk in split_text(text):
            chunks.append(
                {
                    "id": f"{file_id}-{page or 'text'}-{next_index}",
                    "course_id": course_id,
                    "file_id": file_id,
                    "file_name": file_name,
                    "page": page,
                    "chunk_index": next_index,
                    "text": text_chunk,
                    "tokens": tokenize(text_chunk),
                }
            )
            next_index += 1
        return next_index

    def _material_chunks(self, course_id: str) -> List[Dict]:
        return [
            chunk
            for chunk in self._load(course_id)
            if not GENERATED_ARTIFACT_RE.fullmatch(chunk.get("file_name", ""))
        ]


def _summarize_evidence(query: str, hits: Iterable[Dict]) -> str:
    first = next(iter(hits))
    text = first["text"]
    if len(text) > 260:
        text = text[:260] + "..."
    return f"问题“{query}”与资料《{first['file_name']}》中的内容最相关。{text}"


def citation_from_chunk(chunk: Dict) -> Dict:
    return {
        "source_type": "local",
        "file_id": chunk["file_id"],
        "file_name": chunk["file_name"],
        "page": chunk.get("page"),
        "chunk_index": chunk["chunk_index"],
        "score": chunk.get("score", 0),
        "quote": chunk.get("context_text", chunk["text"])[:600],
    }


def _query_phrases(query: str) -> List[str]:
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


def _normalize_query(query: str) -> str:
    normalized = query.lower()
    for stopword in sorted(QUERY_STOP_TOKENS, key=len, reverse=True):
        normalized = normalized.replace(stopword, " ")
    return normalized


def _expand_query_tokens(query: str, tokens: Sequence[str]) -> List[str]:
    expanded = list(tokens)
    query_text = query.lower()
    for trigger, additions in QUERY_EXPANSIONS.items():
        trigger_tokens = tokenize(trigger)
        if trigger in query_text or any(token in tokens for token in trigger_tokens):
            expanded.extend(token for addition in additions for token in tokenize(addition))
    return expanded


def _phrase_score(chunk: Dict, phrases: Sequence[str]) -> float:
    text = chunk.get("text", "").lower()
    return sum(len(phrase) * text.count(phrase) for phrase in phrases)


def _metadata_score(chunk: Dict, query_tokens: Sequence[str]) -> float:
    filename_tokens = Counter(tokenize(chunk.get("file_name", "")))
    return sum(filename_tokens[token] for token in set(query_tokens))


def _semantic_score(query: str, query_tokens: Sequence[str], chunk: Dict) -> float:
    text = f"{chunk.get('file_name', '')} {chunk.get('text', '')}".lower()
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
    query_features = _semantic_features(query)
    chunk_features = _semantic_features(text)
    if query_features and chunk_features:
        overlap = query_features & chunk_features
        score += len(overlap) / ((len(query_features) * len(chunk_features)) ** 0.5)
    return score


def _semantic_features(text: str) -> set[str]:
    features = set()
    for token in tokenize(text):
        if len(token) >= 2 and token not in QUERY_STOP_TOKENS:
            features.add(token)
    compact = re.sub(r"\s+", "", text.lower())
    features.update(compact[index : index + 4] for index in range(max(0, len(compact) - 3)))
    return features


def _reciprocal_rank_fusion(rankings: Sequence[Sequence[Dict]], candidate_limit: int, k: int = 60) -> List[Dict]:
    fused: Dict[str, Dict] = {}
    for ranking in rankings:
        for rank, item in enumerate(ranking[:candidate_limit], start=1):
            key = item["id"]
            if key not in fused:
                fused[key] = dict(item)
                fused[key]["rrf_score"] = 0.0
            fused[key]["rrf_score"] += 1 / (k + rank)
    return sorted(fused.values(), key=lambda item: item["rrf_score"], reverse=True)[:candidate_limit]


def _select_diverse(candidates: Sequence[Dict], limit: int) -> List[Dict]:
    selected: List[Dict] = []
    remaining = list(candidates)
    max_score = max((item["rrf_score"] for item in remaining), default=1)
    while remaining and len(selected) < limit:
        def utility(item: Dict) -> float:
            relevance = item["rrf_score"] / max_score
            redundancy = max((_token_similarity(item, chosen) for chosen in selected), default=0)
            source_bonus = 0.12 if selected and all(item["file_id"] != chosen["file_id"] for chosen in selected) else 0
            return 0.78 * relevance - 0.22 * redundancy + source_bonus

        best = max(remaining, key=utility)
        selected.append(best)
        remaining.remove(best)
    return selected


def _token_similarity(left: Dict, right: Dict) -> float:
    left_tokens = set(left.get("tokens", []))
    right_tokens = set(right.get("tokens", []))
    union = left_tokens | right_tokens
    return len(left_tokens & right_tokens) / len(union) if union else 0


def _neighbor_context(item: Dict, chunks: Sequence[Dict]) -> str:
    position = next((index for index, chunk in enumerate(chunks) if chunk.get("id") == item.get("id")), None)
    if position is None:
        return item["text"]
    related = []
    for index in range(max(0, position - 1), min(len(chunks), position + 2)):
        chunk = chunks[index]
        if chunk.get("file_id") == item.get("file_id") and chunk.get("page") == item.get("page"):
            related.append(chunk["text"])
    return "\n".join(related)


def _pick_keyword(text: str) -> str:
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
