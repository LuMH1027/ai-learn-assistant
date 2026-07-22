from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Protocol

from local_course_agent.retrieval.embeddings.utils import model_fingerprint


class EmbeddingRequestError(RuntimeError):
    """Raised when an external embedding provider cannot return valid vectors."""


class VectorIndexCompatibilityError(RuntimeError):
    """Raised when a persisted vector index was built with another embedding model."""


class EmbeddingModel(Protocol):
    model_id: str
    dimensions: int

    def embed(self, text: str) -> List[float]:
        ...

    def embed_many(self, texts: Iterable[str]) -> List[List[float]]:
        ...


def embedding_model_metadata(model: EmbeddingModel) -> Dict[str, Any]:
    metadata = {
        "type": model.model_id,
        "dimensions": model.dimensions,
        "fingerprint": getattr(model, "fingerprint", model_fingerprint("generic", "", model.model_id)),
    }
    base_url = getattr(model, "base_url", "")
    if base_url:
        metadata["base_url"] = base_url
    return metadata


def default_model_for_saved_index(model_info: Mapping[str, Any], dimensions: int) -> EmbeddingModel:
    from local_course_agent.retrieval.embeddings.fake import FakeEmbeddingModel

    model_id = str(model_info.get("type") or "")
    if not model_id or model_id == FakeEmbeddingModel.model_id:
        return FakeEmbeddingModel(dimensions=dimensions)
    raise VectorIndexCompatibilityError(
        f"vector index was built with {model_id}; provide a matching embedding model or rebuild vector index"
    )


def validate_saved_model_compatibility(
    model_info: Mapping[str, Any],
    model: EmbeddingModel,
    dimensions: int,
) -> None:
    saved_type = str(model_info.get("type") or "")
    current_type = str(getattr(model, "model_id", ""))
    if saved_type and saved_type != current_type:
        raise VectorIndexCompatibilityError(
            f"vector index embedding model mismatch: stored {saved_type}, configured {current_type}; "
            "rebuild vector index"
        )
    saved_fingerprint = str(model_info.get("fingerprint") or "")
    current_fingerprint = str(getattr(model, "fingerprint", ""))
    if saved_fingerprint and current_fingerprint and saved_fingerprint != current_fingerprint:
        saved_base_url = str(model_info.get("base_url") or "")
        current_base_url = str(getattr(model, "base_url", "") or "")
        raise VectorIndexCompatibilityError(
            "vector index embedding fingerprint mismatch: "
            f"stored base_url={saved_base_url or '<none>'}, configured base_url={current_base_url or '<none>'}; "
            "rebuild vector index"
        )
    current_dimensions = int(getattr(model, "dimensions", 0) or 0)
    if current_dimensions and dimensions != current_dimensions:
        raise VectorIndexCompatibilityError(
            f"vector index embedding dimension mismatch: stored {dimensions}, configured {current_dimensions}; "
            "rebuild vector index"
        )
