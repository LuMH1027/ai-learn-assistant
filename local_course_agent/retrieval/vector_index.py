from __future__ import annotations

import hashlib
import json
import math
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Protocol, Sequence


SCHEMA_VERSION = 1
DEFAULT_DIMENSIONS = 64


class EmbeddingModel(Protocol):
    model_id: str
    dimensions: int

    def embed(self, text: str) -> List[float]:
        ...

    def embed_many(self, texts: Iterable[str]) -> List[List[float]]:
        ...


@dataclass
class VectorDocument:
    id: str
    text: str
    metadata: Dict
    vector: List[float]


@dataclass
class VectorSearchResult:
    id: str
    text: str
    metadata: Dict
    score: float


class FakeEmbeddingModel:
    """Deterministic hash-based embedding used until a real model is wired in."""

    model_id = "fake-hash-embedding-v1"

    def __init__(self, dimensions: int = DEFAULT_DIMENSIONS):
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.dimensions = dimensions

    def embed(self, text: str) -> List[float]:
        vector = [0.0] * self.dimensions
        for token in _tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        return _unit_vector(vector)

    def embed_many(self, texts: Iterable[str]) -> List[List[float]]:
        return [self.embed(text) for text in texts]


class OpenAICompatibleEmbeddingModel:
    """OpenAI-compatible `/embeddings` client for production vector retrieval."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        dimensions: int | None = None,
        timeout: float = 30.0,
    ):
        if not base_url or not api_key or not model:
            raise ValueError("base_url, api_key, and model are required")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.model_id = f"openai-compatible:{model}"
        self.dimensions = int(dimensions or 0)
        self.timeout = float(timeout)

    def embed(self, text: str) -> List[float]:
        return self.embed_many([text])[0]

    def embed_many(self, texts: Iterable[str]) -> List[List[float]]:
        items = [str(text) for text in texts]
        if not items:
            return []
        payload = json.dumps({"model": self.model, "input": items}).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/embeddings",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                raw = response.read().decode("utf-8")
        except urllib.error.URLError as exc:
            raise RuntimeError(f"embedding request failed: {exc}") from exc
        parsed = json.loads(raw)
        data = sorted(parsed.get("data", []), key=lambda item: int(item.get("index", 0)))
        vectors = [[float(value) for value in item.get("embedding", [])] for item in data]
        if len(vectors) != len(items):
            raise RuntimeError("embedding response count mismatch")
        if not vectors or not vectors[0]:
            raise RuntimeError("embedding response is empty")
        dimensions = len(vectors[0])
        if self.dimensions and dimensions != self.dimensions:
            raise RuntimeError(f"embedding dimension mismatch: expected {self.dimensions}, got {dimensions}")
        self.dimensions = dimensions
        return [_unit_vector(vector) for vector in vectors]


def create_embedding_model(config: Mapping[str, Any] | None = None) -> EmbeddingModel:
    config = dict(config or {})
    embedding_model = str(config.get("embedding_model") or "").strip()
    api_key = str(config.get("embedding_api_key") or config.get("api_key") or "").strip()
    base_url = str(config.get("embedding_base_url") or config.get("base_url") or "").strip()
    if embedding_model and api_key and base_url:
        return OpenAICompatibleEmbeddingModel(
            base_url=base_url,
            api_key=api_key,
            model=embedding_model,
            dimensions=_optional_int(config.get("embedding_dimensions")),
            timeout=float(config.get("embedding_timeout") or config.get("timeout") or 30),
        )
    return FakeEmbeddingModel(dimensions=int(config.get("fake_embedding_dimensions") or DEFAULT_DIMENSIONS))


class VectorIndex:
    def __init__(self, embedding_model: Optional[EmbeddingModel] = None):
        self.embedding_model = embedding_model or FakeEmbeddingModel()
        self.documents: List[VectorDocument] = []

    def add(self, document_id: str, text: str, metadata: Optional[Dict] = None, vector: Optional[Sequence[float]] = None) -> None:
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
        path = Path(path)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "embedding_model": {
                "type": self.embedding_model.model_id,
                "dimensions": self.embedding_model.dimensions,
            },
            "documents": [asdict(document) for document in self.documents],
        }
        _atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))

    @classmethod
    def load(cls, path: Path, embedding_model: Optional[EmbeddingModel] = None) -> "VectorIndex":
        path = Path(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        model_info = payload.get("embedding_model") or {}
        dimensions = int(model_info.get("dimensions") or DEFAULT_DIMENSIONS)
        model = embedding_model or FakeEmbeddingModel(dimensions=dimensions)
        if getattr(model, "dimensions", 0) == 0:
            model.dimensions = dimensions
        index = cls(model)

        for raw in payload.get("documents", []):
            index.add(
                document_id=str(raw["id"]),
                text=str(raw.get("text", "")),
                metadata=dict(raw.get("metadata") or {}),
                vector=[float(value) for value in raw.get("vector", [])],
            )
        return index

    def _validate_dimensions(self, vector: Sequence[float]) -> None:
        if len(vector) != self.embedding_model.dimensions:
            raise ValueError(
                f"vector dimension mismatch: expected {self.embedding_model.dimensions}, got {len(vector)}"
            )


def build_vector_index_from_chunks(chunks: Sequence[Mapping[str, Any]], embedding_model: Optional[EmbeddingModel] = None) -> VectorIndex:
    index = VectorIndex(embedding_model)
    prepared = []
    for position, chunk in enumerate(chunks):
        text = _chunk_text(chunk)
        if not text.strip():
            continue
        document_id = _chunk_id(chunk, position)
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


def hybrid_merge_lexical_vector(
    lexical_hits: Sequence[Any],
    vector_hits: Sequence[Any],
    limit: int = 5,
) -> List[Dict]:
    if limit <= 0:
        return []

    fused: Dict[str, Dict] = {}
    rrf_k = 60

    for rank, raw_hit in enumerate(lexical_hits, start=1):
        hit = _normalize_hit(raw_hit, source="lexical")
        key = _hit_key(hit, rank)
        current = fused.setdefault(key, hit)
        if current is not hit:
            _merge_missing_fields(current, hit)
        current["lexical_rank"] = rank
        current["lexical_score"] = _numeric_score(hit.get("score"), hit.get("rrf_score"), hit.get("bm25_score"))
        current.setdefault("retrieval_sources", [])
        if "lexical" not in current["retrieval_sources"]:
            current["retrieval_sources"].append("lexical")
        current["hybrid_rrf_score"] = current.get("hybrid_rrf_score", 0.0) + 1 / (rrf_k + rank)

    for rank, raw_hit in enumerate(vector_hits, start=1):
        hit = _normalize_hit(raw_hit, source="vector")
        key = _hit_key(hit, rank)
        current = fused.setdefault(key, hit)
        if current is not hit:
            _merge_missing_fields(current, hit)
        current["vector_rank"] = rank
        current["vector_score"] = _numeric_score(hit.get("vector_score"), hit.get("score"))
        current.setdefault("retrieval_sources", [])
        if "vector" not in current["retrieval_sources"]:
            current["retrieval_sources"].append("vector")
        current["hybrid_rrf_score"] = current.get("hybrid_rrf_score", 0.0) + 1 / (rrf_k + rank)

    merged = list(fused.values())
    for hit in merged:
        hit["score"] = round(hit.get("hybrid_rrf_score", 0.0) * 1000, 4)
        hit["retrieval_method"] = _merged_retrieval_method(hit)

    merged.sort(
        key=lambda hit: (
            hit.get("hybrid_rrf_score", 0.0),
            "lexical" in hit.get("retrieval_sources", []),
            hit.get("vector_score", float("-inf")),
            hit.get("lexical_score", float("-inf")),
        ),
        reverse=True,
    )
    return merged[:limit]


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right):
        raise ValueError("vectors must have the same dimensions")
    if not left:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return sum(a * b for a, b in zip(left, right)) / (left_norm * right_norm)


def _chunk_text(chunk: Mapping[str, Any]) -> str:
    return str(chunk.get("text") or chunk.get("context_text") or chunk.get("content") or "")


def _chunk_id(chunk: Mapping[str, Any], position: int) -> str:
    if chunk.get("id"):
        return str(chunk["id"])
    file_id = str(chunk.get("file_id") or chunk.get("file_name") or "chunk")
    page = str(chunk.get("page") if chunk.get("page") is not None else "text")
    chunk_index = str(chunk.get("chunk_index") if chunk.get("chunk_index") is not None else position + 1)
    return f"{file_id}-{page}-{chunk_index}"


def _normalize_hit(raw_hit: Any, source: str) -> Dict:
    if isinstance(raw_hit, Mapping):
        hit = dict(raw_hit)
    elif isinstance(raw_hit, VectorSearchResult):
        hit = dict(raw_hit.metadata)
        hit["id"] = raw_hit.id
        hit["text"] = raw_hit.text
        hit["vector_score"] = raw_hit.score
    else:
        metadata = dict(getattr(raw_hit, "metadata", {}) or {})
        hit = metadata
        if hasattr(raw_hit, "id"):
            hit["id"] = getattr(raw_hit, "id")
        if hasattr(raw_hit, "text"):
            hit["text"] = getattr(raw_hit, "text")
        if hasattr(raw_hit, "score"):
            score = getattr(raw_hit, "score")
            hit["vector_score" if source == "vector" else "score"] = score
    if source == "vector" and "vector_score" not in hit and "score" in hit:
        hit["vector_score"] = hit["score"]
    if "id" not in hit or not hit["id"]:
        hit["id"] = _chunk_id(hit, 0)
    if "text" not in hit:
        hit["text"] = _chunk_text(hit)
    return hit


def _hit_key(hit: Mapping[str, Any], fallback_rank: int) -> str:
    if hit.get("id"):
        return str(hit["id"])
    if hit.get("file_id") is not None and hit.get("chunk_index") is not None:
        return f"{hit.get('file_id')}:{hit.get('page')}:{hit.get('chunk_index')}"
    if hit.get("file_name") is not None and hit.get("chunk_index") is not None:
        return f"{hit.get('file_name')}:{hit.get('page')}:{hit.get('chunk_index')}"
    return f"hit:{fallback_rank}"


def _merge_missing_fields(target: Dict, source: Mapping[str, Any]) -> None:
    for key, value in source.items():
        if key not in target or target[key] in (None, "", []):
            target[key] = value


def _numeric_score(*values: Any) -> float:
    for value in values:
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _merged_retrieval_method(hit: Mapping[str, Any]) -> str:
    sources = hit.get("retrieval_sources", [])
    if "lexical" in sources and "vector" in sources:
        return "hybrid_lexical_vector_rrf"
    if "vector" in sources:
        return "vector"
    return str(hit.get("retrieval_method") or "lexical")


def _tokens(text: str) -> List[str]:
    normalized = text.lower()
    tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", normalized)
    cjk_chars = [token for token in tokens if len(token) == 1 and "\u4e00" <= token <= "\u9fff"]
    cjk_bigrams = [a + b for a, b in zip(cjk_chars, cjk_chars[1:])]
    return tokens + cjk_bigrams


def _unit_vector(vector: Sequence[float]) -> List[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return [0.0 for _ in vector]
    return [value / norm for value in vector]


def _optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
