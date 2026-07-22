from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Sequence

from local_course_agent.retrieval.embeddings import EmbeddingModel, FakeEmbeddingModel
from local_course_agent.retrieval.vector.math import cosine_similarity
from local_course_agent.retrieval.vector.persistence import load_documents, save_documents
from local_course_agent.retrieval.vector.schema import VectorDocument, VectorSearchResult


class VectorIndex:
    def __init__(self, embedding_model: Optional[EmbeddingModel] = None):
        self.embedding_model = embedding_model or FakeEmbeddingModel()
        self.documents: List[VectorDocument] = []

    def add(
        self,
        document_id: str,
        text: str,
        metadata: Optional[Dict] = None,
        vector: Optional[Sequence[float]] = None,
    ) -> None:
        if not document_id:
            raise ValueError("document_id is required")
        if vector is None:
            document_vector = self.embedding_model.embed(text)
        else:
            document_vector = [float(value) for value in vector]
        self._validate_dimensions(document_vector)

        document = VectorDocument(
            id=document_id,
            text=text,
            metadata=dict(metadata or {}),
            vector=document_vector,
        )
        for index, current in enumerate(self.documents):
            if current.id == document_id:
                self.documents[index] = document
                return
        self.documents.append(document)

    def search(self, query: str, limit: int = 5, min_score: Optional[float] = None) -> List[VectorSearchResult]:
        if limit <= 0 or not self.documents:
            return []
        query_vector = self.embedding_model.embed(query)
        self._validate_dimensions(query_vector)
        scored = []
        for order, document in enumerate(self.documents):
            score = cosine_similarity(query_vector, document.vector)
            if min_score is None or score >= min_score:
                scored.append(
                    (
                        score,
                        -order,
                        VectorSearchResult(
                            id=document.id,
                            text=document.text,
                            metadata=dict(document.metadata),
                            score=score,
                        ),
                    )
                )
        scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [item[2] for item in scored[:limit]]

    def save(self, path: Path) -> None:
        save_documents(Path(path), self.documents, self.embedding_model)

    @classmethod
    def load(cls, path: Path, embedding_model: Optional[EmbeddingModel] = None) -> "VectorIndex":
        model, documents = load_documents(Path(path), embedding_model)
        index = cls(model)
        index.documents = documents
        return index

    def _validate_dimensions(self, vector: Sequence[float]) -> None:
        if len(vector) != self.embedding_model.dimensions:
            raise ValueError(
                f"vector dimension mismatch: expected {self.embedding_model.dimensions}, got {len(vector)}"
            )
