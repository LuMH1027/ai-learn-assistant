from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from local_course_agent.retrieval.chunking import (
    INDEX_TOKENIZER_VERSION,
    material_type,
    split_structured_text,
    split_text,
    tokenize,
)
from local_course_agent.retrieval.ranking import (
    compact_sentence,
    expand_query_tokens,
    indexable_chunk_text,
    neighbor_context,
    normalize_query,
    pick_keyword,
    rank_candidates,
    representative_chunks,
    retrieval_quality,
    retrieval_trace,
    select_diverse,
    select_hybrid_vector_hits,
)
from local_course_agent.retrieval.vector_index import (
    VectorIndex,
    build_vector_index_from_chunks,
    create_embedding_model,
)


GENERATED_ARTIFACT_RE = re.compile(r"^(?:课程摘要|练习题)-\d{8}-\d{6}\.md$", re.IGNORECASE)
INDEX_SCHEMA_VERSION = 2


class CourseKnowledgeBase:
    """A lightweight local RAG store with per-course isolation.

    It intentionally uses JSON files and lexical scoring so the project can run
    on a fresh Windows machine before optional vector-search upgrades.
    """

    def __init__(self, storage_dir: Path, embedding_model=None):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.embedding_model = embedding_model or create_embedding_model({})

    def configure_embeddings(self, ai_config: dict | None = None) -> None:
        self.embedding_model = create_embedding_model(ai_config or {})

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
                    file_path=document.get("path", ""),
                    next_index=next_index,
                )
        self._save(course_id, chunks)
        return len(chunks)

    def clear_course(self, course_id: str) -> None:
        self._save(course_id, [])

    def search(self, course_id: str, query: str, limit: int = 5, strategy: str = "lexical") -> List[Dict]:
        normalized_query = normalize_query(query)
        original_query_tokens = [
            token
            for token in tokenize(normalized_query)
            if not (token.isdigit() and len(token) < 4)
        ]
        query_tokens = expand_query_tokens(normalized_query, original_query_tokens) if strategy == "hybrid" else original_query_tokens
        if not query_tokens:
            return []
        chunks = self._material_chunks(course_id)
        for chunk in chunks:
            # Existing indexes are upgraded lazily after tokenizer changes.
            chunk["section_title"] = chunk.get("section_title", "")
            chunk["material_type"] = chunk.get("material_type") or material_type(chunk.get("file_name", ""), chunk.get("file_path", ""))
            chunk["tokens"] = tokenize(indexable_chunk_text(chunk))
        if not chunks:
            return []
        candidates = rank_candidates(chunks, normalized_query, query_tokens, limit)
        selected = (
            select_hybrid_vector_hits(
                chunks,
                candidates,
                normalized_query,
                limit,
                vector_index=self._load_or_build_vector_index(course_id, chunks),
            )
            if strategy == "hybrid"
            else select_diverse(candidates, limit)
        )
        for item in selected:
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
        max_score = max((hit.get("score", 0) for hit in hits), default=0)
        quality = retrieval_quality(max_coverage, max_score, len(hits))
        return {
            "answer": answer,
            "citations": citations,
            "mode": "grounded",
            "retrieval_quality": quality,
            "retrieval_trace": retrieval_trace(hits),
        }

    def generate_summary(self, course_id: str, limit: int = 6) -> Dict:
        chunks = self.summary_chunks(course_id, limit)
        if not chunks:
            return {"content": "当前课程还没有可用于生成摘要的资料片段，请先构建知识库。", "citations": []}
        citations = [citation_from_chunk(chunk) for chunk in chunks]
        points = ["课程复习摘要", "", "## 核心知识点"]
        for chunk in chunks:
            keyword = pick_keyword(chunk["text"])
            points.append(f"- {keyword}：{compact_sentence(chunk['text'])}（来源：《{chunk['file_name']}》）")
        points.extend(["", "## 复习建议"])
        points.append("- 先按上面的核心知识点复述定义，再回到来源文件核对例子、条件和易错边界。")
        return {
            "content": "\n".join(points),
            "citations": citations,
        }

    def summary_chunks(self, course_id: str, limit: int = 6) -> List[Dict]:
        return representative_chunks(self._material_chunks(course_id), limit)

    def generate_quiz(self, course_id: str, count: int = 5) -> Dict:
        chunks = representative_chunks(self._material_chunks(course_id), count)
        if not chunks:
            return {"content": "当前课程还没有可用于生成练习题的资料片段，请先构建知识库。", "citations": []}
        questions = ["课程自测题"]
        for index, chunk in enumerate(chunks, start=1):
            keyword = pick_keyword(chunk["text"])
            questions.append(
                f"{index}. 基础题：说明“{keyword}”的含义或作用，并指出它解决了什么问题。\n"
                f"   应用题：结合《{chunk['file_name']}》中的材料，举一个使用“{keyword}”的场景。\n"
                f"   参考要点：{compact_sentence(chunk['text'])}"
            )
        return {
            "content": "\n\n".join(questions),
            "citations": [citation_from_chunk(chunk) for chunk in chunks],
        }

    def _path(self, course_id: str) -> Path:
        return self.storage_dir / f"{course_id}.json"

    def _vector_path(self, course_id: str) -> Path:
        return self.storage_dir / f"{course_id}.vector.json"

    def _load(self, course_id: str) -> List[Dict]:
        path = self._path(course_id)
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload.get("chunks", [])
        return payload

    def _save(self, course_id: str, chunks: List[Dict]) -> None:
        payload = {
            "schema_version": INDEX_SCHEMA_VERSION,
            "tokenizer_version": INDEX_TOKENIZER_VERSION,
            "chunks": chunks,
        }
        _atomic_write_text(self._path(course_id), json.dumps(payload, ensure_ascii=False, indent=2))
        self._save_vector_index(course_id, chunks)

    def _append_text_chunks(
        self,
        chunks: List[Dict],
        course_id: str,
        file_id: str,
        file_name: str,
        text: str,
        page=None,
        file_path: str = "",
        next_index: int = 1,
    ) -> int:
        for structured_chunk in split_structured_text(text):
            text_chunk = structured_chunk["text"]
            section_title = structured_chunk.get("section_title", "")
            indexed_text = f"{section_title}\n{text_chunk}" if section_title else text_chunk
            chunks.append(
                {
                    "id": f"{file_id}-{page or 'text'}-{next_index}",
                    "course_id": course_id,
                    "file_id": file_id,
                    "file_name": file_name,
                    "file_path": file_path,
                    "section_title": section_title,
                    "material_type": material_type(file_name, file_path),
                    "page": page,
                    "chunk_index": next_index,
                    "text": text_chunk,
                    "tokens": tokenize(indexed_text),
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

    def _save_vector_index(self, course_id: str, chunks: Sequence[Dict]) -> None:
        try:
            vector_index = build_vector_index_from_chunks(chunks, self.embedding_model)
            vector_index.save(self._vector_path(course_id))
        except Exception:
            # Lexical indexes remain authoritative; embedding failures should
            # degrade retrieval, not break course indexing.
            return

    def _load_or_build_vector_index(self, course_id: str, chunks: Sequence[Dict]) -> VectorIndex | None:
        path = self._vector_path(course_id)
        if path.exists():
            try:
                index = VectorIndex.load(path, embedding_model=self.embedding_model)
                if len(index.documents) == len([chunk for chunk in chunks if chunk.get("text")]):
                    return index
            except Exception:
                pass
        try:
            vector_index = build_vector_index_from_chunks(chunks, self.embedding_model)
        except Exception:
            return None
        try:
            vector_index.save(path)
        except Exception:
            pass
        return vector_index


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
        "section_title": chunk.get("section_title", ""),
        "material_type": chunk.get("material_type", ""),
        "page": chunk.get("page"),
        "chunk_index": chunk["chunk_index"],
        "score": chunk.get("score", 0),
        "quote": chunk.get("context_text", chunk["text"])[:600],
    }


def _atomic_write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)
