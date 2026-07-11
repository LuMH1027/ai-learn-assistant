from __future__ import annotations

import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


def tokenize(text: str) -> List[str]:
    return [token.lower() for token in TOKEN_RE.findall(text)]


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
        chunks = self._load(course_id)
        chunks = [chunk for chunk in chunks if not (chunk["file_id"] == file_id and chunk.get("page") == page)]
        next_index = len(chunks) + 1
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
        self._save(course_id, chunks)
        return len(chunks)

    def clear_course(self, course_id: str) -> None:
        self._path(course_id).write_text("[]", encoding="utf-8")

    def search(self, course_id: str, query: str, limit: int = 5) -> List[Dict]:
        query_tokens = tokenize(query)
        if not query_tokens:
            return []
        query_counter = Counter(query_tokens)
        chunks = self._load(course_id)
        total_docs = max(len(chunks), 1)
        document_frequency = Counter()
        for chunk in chunks:
            document_frequency.update(set(chunk["tokens"]))

        scored = []
        for chunk in chunks:
            chunk_counter = Counter(chunk["tokens"])
            score = 0.0
            for token, query_weight in query_counter.items():
                if token not in chunk_counter:
                    continue
                idf = math.log((total_docs + 1) / (document_frequency[token] + 1)) + 1
                score += query_weight * chunk_counter[token] * idf
            if score > 0:
                item = dict(chunk)
                item["score"] = round(score, 4)
                scored.append(item)
        scored.sort(key=lambda item: item["score"], reverse=True)
        return scored[:limit]

    def answer(self, course_id: str, query: str) -> Dict:
        hits = self.search(course_id, query, limit=4)
        if not hits:
            return {
                "answer": "未在当前课程资料中找到可靠依据。建议先确认该课程资料是否已完成入库，或换一种更贴近资料原文的提问方式。",
                "citations": [],
                "mode": "no_basis",
            }

        citations = [
            {
                "file_id": hit["file_id"],
                "file_name": hit["file_name"],
                "page": hit.get("page"),
                "chunk_index": hit["chunk_index"],
                "score": hit["score"],
                "quote": hit["text"][:180],
            }
            for hit in hits
        ]
        evidence = "\n".join(f"{idx}. {hit['text']}" for idx, hit in enumerate(hits, start=1))
        answer = (
            "基于当前课程资料，可以这样理解：\n"
            f"{_summarize_evidence(query, hits)}\n\n"
            "依据片段：\n"
            f"{evidence}"
        )
        return {"answer": answer, "citations": citations, "mode": "grounded"}

    def generate_summary(self, course_id: str, limit: int = 6) -> Dict:
        chunks = self._load(course_id)[:limit]
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
        chunks = self._load(course_id)[:count]
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


def _summarize_evidence(query: str, hits: Iterable[Dict]) -> str:
    first = next(iter(hits))
    text = first["text"]
    if len(text) > 260:
        text = text[:260] + "..."
    return f"问题“{query}”与资料《{first['file_name']}》中的内容最相关。{text}"


def citation_from_chunk(chunk: Dict) -> Dict:
    return {
        "file_id": chunk["file_id"],
        "file_name": chunk["file_name"],
        "page": chunk.get("page"),
        "chunk_index": chunk["chunk_index"],
        "score": chunk.get("score", 0),
        "quote": chunk["text"][:180],
    }


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
