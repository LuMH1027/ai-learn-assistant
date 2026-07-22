from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, Sequence

from local_course_agent.retrieval.vector_index import VectorIndex


VectorIndexBuilder = Callable[[Sequence[Dict], object], VectorIndex]


class RagVectorCache:
    """Persistent vector sidecar management for course RAG indexes."""

    def __init__(self, vector_path_for_course: Callable[[str], Path], embedding_model):
        self._vector_path_for_course = vector_path_for_course
        self.embedding_model = embedding_model

    def save(self, course_id: str, chunks: Sequence[Dict], build_vector_index: VectorIndexBuilder) -> None:
        try:
            vector_index = build_vector_index(chunks, self.embedding_model)
            vector_index.save(self._vector_path_for_course(course_id))
        except Exception:
            # Lexical indexes remain authoritative; embedding failures should
            # degrade retrieval, not break course indexing.
            return

    def load_or_build(
        self,
        course_id: str,
        chunks: Sequence[Dict],
        build_vector_index: VectorIndexBuilder,
    ) -> VectorIndex | None:
        path = self._vector_path_for_course(course_id)
        if path.exists():
            try:
                index = VectorIndex.load(path, embedding_model=self.embedding_model)
                if len(index.documents) == len([chunk for chunk in chunks if chunk.get("text")]):
                    return index
            except Exception:
                pass
        try:
            vector_index = build_vector_index(chunks, self.embedding_model)
        except Exception:
            return None
        try:
            vector_index.save(path)
        except Exception:
            pass
        return vector_index
