from __future__ import annotations

from typing import Any, Mapping, Optional, Sequence

from local_course_agent.retrieval.embeddings import EmbeddingModel
from local_course_agent.retrieval.vector.index import VectorIndex


def build_vector_index_from_chunks(
    chunks: Sequence[Mapping[str, Any]],
    embedding_model: Optional[EmbeddingModel] = None,
) -> VectorIndex:
    index = VectorIndex(embedding_model)
    prepared = []
    for position, chunk in enumerate(chunks):
        text = chunk_text(chunk)
        if not text.strip():
            continue
        document_id = chunk_id(chunk, position)
        metadata = {
            key: value
            for key, value in dict(chunk).items()
            if key not in {"tokens", "context_text"}
        }
        metadata["id"] = document_id
        prepared.append((document_id, text, metadata))
    vectors = index.embedding_model.embed_many(text for _, text, _ in prepared)
    if len(vectors) != len(prepared):
        raise RuntimeError("embedding vector count mismatch")
    for (document_id, text, metadata), vector in zip(prepared, vectors):
        index.add(document_id, text, metadata, vector=vector)
    return index


def chunk_text(chunk: Mapping[str, Any]) -> str:
    return str(chunk.get("text") or chunk.get("context_text") or chunk.get("content") or "")


def chunk_id(chunk: Mapping[str, Any], position: int) -> str:
    if chunk.get("id"):
        return str(chunk["id"])
    file_id = str(chunk.get("file_id") or chunk.get("file_name") or "chunk")
    page = str(chunk.get("page") if chunk.get("page") is not None else "text")
    chunk_index = str(chunk.get("chunk_index") if chunk.get("chunk_index") is not None else position + 1)
    return f"{file_id}-{page}-{chunk_index}"
