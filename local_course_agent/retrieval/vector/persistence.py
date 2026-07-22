from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

from local_course_agent.retrieval.embeddings import (
    DEFAULT_DIMENSIONS,
    EmbeddingModel,
    VectorIndexCompatibilityError,
    default_model_for_saved_index,
    embedding_model_metadata,
    validate_saved_model_compatibility,
)
from local_course_agent.retrieval.vector.schema import SCHEMA_VERSION, VectorDocument


def save_documents(path: Path, documents: Sequence[VectorDocument], embedding_model: EmbeddingModel) -> None:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "embedding_model": embedding_model_metadata(embedding_model),
        "documents": [asdict(document) for document in documents],
    }
    atomic_write_text(Path(path), json.dumps(payload, ensure_ascii=False, indent=2))


def load_documents(
    path: Path,
    embedding_model: Optional[EmbeddingModel] = None,
) -> Tuple[EmbeddingModel, List[VectorDocument]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    model_info = payload.get("embedding_model") or {}
    raw_dimensions = model_info.get("dimensions")
    dimensions = int(raw_dimensions) if raw_dimensions not in (None, "") else DEFAULT_DIMENSIONS
    model = embedding_model or default_model_for_saved_index(model_info, dimensions)
    validate_saved_model_compatibility(model_info, model, dimensions)
    if getattr(model, "dimensions", 0) == 0:
        model.dimensions = dimensions

    documents = []
    for raw in payload.get("documents", []):
        document_id = str(raw["id"])
        vector = [float(value) for value in raw.get("vector", [])]
        if len(vector) != dimensions:
            raise VectorIndexCompatibilityError(
                f"stored vector dimension mismatch for document {document_id}: "
                f"index metadata says {dimensions}, vector has {len(vector)}; rebuild vector index"
            )
        documents.append(
            VectorDocument(
                id=document_id,
                text=str(raw.get("text", "")),
                metadata=dict(raw.get("metadata") or {}),
                vector=vector,
            )
        )
    return model, documents


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
