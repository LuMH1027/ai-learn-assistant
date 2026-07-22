from __future__ import annotations

from importlib import import_module
from pathlib import Path
from typing import Dict, List, Sequence

from local_course_agent.retrieval.rag.answering import grounded_answer, no_basis_answer
from local_course_agent.retrieval.rag.artifacts import generate_quiz_from_chunks, generate_summary_from_chunks
from local_course_agent.retrieval.rag.indexing import append_text_chunks, build_document_chunks
from local_course_agent.retrieval.rag.search import search_course_chunks
from local_course_agent.retrieval.rag.store import KnowledgeChunkStore
from local_course_agent.retrieval.rag.vector_cache import RagVectorCache
from local_course_agent.retrieval.ranking import representative_chunks
from local_course_agent.retrieval.reranking import CandidateReranker
from local_course_agent.retrieval.vector_index import VectorIndex, create_embedding_model


class CourseKnowledgeBase:
    """Per-course RAG facade.

    Storage, chunk construction, vector sidecars, and generated artifacts live
    in narrow retrieval modules; this class keeps the public API stable.
    """

    def __init__(
        self,
        storage_dir: Path,
        embedding_model=None,
        reranker: CandidateReranker | None = None,
        reranker_config: dict | None = None,
    ):
        self.store = KnowledgeChunkStore(Path(storage_dir))
        self.storage_dir = self.store.storage_dir
        self.embedding_model = embedding_model or create_embedding_model({})
        self.vector_cache = RagVectorCache(self.store.vector_path, self.embedding_model)
        self.reranker = reranker
        self.reranker_config = dict(reranker_config or {})

    def configure_embeddings(self, ai_config: dict | None = None) -> None:
        self.embedding_model = create_embedding_model(ai_config or {})
        self.vector_cache.embedding_model = self.embedding_model

    def configure_reranker(self, reranker: CandidateReranker | None = None, config: dict | None = None) -> None:
        self.reranker = reranker
        self.reranker_config = dict(config or {})

    def index_text(self, course_id: str, file_id: str, file_name: str, text: str, page=None) -> int:
        chunks = self._material_chunks(course_id)
        chunks = [chunk for chunk in chunks if not (chunk["file_id"] == file_id and chunk.get("page") == page)]
        append_text_chunks(
            chunks,
            course_id=course_id,
            file_id=file_id,
            file_name=file_name,
            text=text,
            page=page,
            next_index=len(chunks) + 1,
        )
        self._save(course_id, chunks)
        return len(chunks)

    def rebuild_course(self, course_id: str, documents: Sequence[Dict]) -> int:
        chunks = build_document_chunks(course_id, documents)
        self._save(course_id, chunks)
        return len(chunks)

    def clear_course(self, course_id: str) -> None:
        self._save(course_id, [])

    def search(self, course_id: str, query: str, limit: int = 5, strategy: str = "lexical") -> List[Dict]:
        return search_course_chunks(
            course_id=course_id,
            chunks=self._material_chunks(course_id),
            query=query,
            limit=limit,
            strategy=strategy,
            vector_index_loader=self._load_or_build_vector_index,
            reranker=self.reranker,
        )

    def answer(self, course_id: str, query: str, strategy: str = "hybrid") -> Dict:
        hits = self.search(course_id, query, limit=4, strategy=strategy)
        if not hits:
            return no_basis_answer()
        return grounded_answer(query, hits)

    def generate_summary(self, course_id: str, limit: int = 6) -> Dict:
        return generate_summary_from_chunks(self.summary_chunks(course_id, limit))

    def summary_chunks(self, course_id: str, limit: int = 6) -> List[Dict]:
        return representative_chunks(self._material_chunks(course_id), limit)

    def generate_quiz(self, course_id: str, count: int = 5) -> Dict:
        chunks = representative_chunks(self._material_chunks(course_id), count)
        return generate_quiz_from_chunks(chunks)

    def _path(self, course_id: str) -> Path:
        return self.store.path(course_id)

    def _vector_path(self, course_id: str) -> Path:
        return self.store.vector_path(course_id)

    def _load(self, course_id: str) -> List[Dict]:
        return self.store.load(course_id)

    def _save(self, course_id: str, chunks: List[Dict]) -> None:
        self.store.save(course_id, chunks)
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
        return append_text_chunks(
            chunks,
            course_id=course_id,
            file_id=file_id,
            file_name=file_name,
            text=text,
            page=page,
            file_path=file_path,
            next_index=next_index,
        )

    def _material_chunks(self, course_id: str) -> List[Dict]:
        return self.store.material_chunks(course_id)

    def _save_vector_index(self, course_id: str, chunks: Sequence[Dict]) -> None:
        self.vector_cache.save(course_id, chunks, self._vector_index_builder())

    def _load_or_build_vector_index(self, course_id: str, chunks: Sequence[Dict]) -> VectorIndex | None:
        return self.vector_cache.load_or_build(course_id, chunks, self._vector_index_builder())

    @staticmethod
    def _vector_index_builder():
        return import_module("local_course_agent.retrieval.rag").build_vector_index_from_chunks


__all__ = ["CourseKnowledgeBase"]
