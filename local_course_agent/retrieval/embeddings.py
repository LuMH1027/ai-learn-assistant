from __future__ import annotations

import hashlib
import json
import math
import re
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Iterable, List, Mapping, Protocol, Sequence


DEFAULT_DIMENSIONS = 64
DEFAULT_EMBEDDING_BATCH_SIZE = 32
DEFAULT_EMBEDDING_MAX_RETRIES = 2
DEFAULT_EMBEDDING_RETRY_DELAY = 1.0


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


class FakeEmbeddingModel:
    """Deterministic hash-based embedding used until a real model is wired in."""

    model_id = "fake-hash-embedding-v1"

    def __init__(self, dimensions: int = DEFAULT_DIMENSIONS):
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.dimensions = dimensions

    @property
    def fingerprint(self) -> str:
        return model_fingerprint("fake-hash", "", self.model_id)

    def embed(self, text: str) -> List[float]:
        vector = [0.0] * self.dimensions
        for token in _tokens(text):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            bucket = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[bucket] += sign
        return unit_vector(vector)

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
        batch_size: int = DEFAULT_EMBEDDING_BATCH_SIZE,
        max_retries: int = DEFAULT_EMBEDDING_MAX_RETRIES,
        retry_delay: float = DEFAULT_EMBEDDING_RETRY_DELAY,
    ):
        if not base_url or not api_key or not model:
            raise ValueError("base_url, api_key, and model are required")
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative")
        if retry_delay < 0:
            raise ValueError("retry_delay cannot be negative")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.model_id = f"openai-compatible:{model}"
        self.dimensions = int(dimensions or 0)
        self.timeout = float(timeout)
        self.batch_size = int(batch_size)
        self.max_retries = int(max_retries)
        self.retry_delay = float(retry_delay)

    @property
    def fingerprint(self) -> str:
        return model_fingerprint("openai-compatible", self.base_url, self.model)

    def embed(self, text: str) -> List[float]:
        return self.embed_many([text])[0]

    def embed_many(self, texts: Iterable[str]) -> List[List[float]]:
        items = [str(text) for text in texts]
        if not items:
            return []
        vectors: List[List[float]] = []
        for start in range(0, len(items), self.batch_size):
            batch = items[start : start + self.batch_size]
            vectors.extend(self._embed_batch(batch, batch_number=start // self.batch_size + 1))
        return vectors

    def _embed_batch(self, items: Sequence[str], batch_number: int) -> List[List[float]]:
        payload = json.dumps({"model": self.model, "input": list(items)}).encode("utf-8")
        raw = self._post_embeddings(payload, batch_number=batch_number)
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise EmbeddingRequestError(
                f"embedding response JSON decode failed for {self.base_url}/embeddings "
                f"(batch {batch_number}): {exc.msg}"
            ) from exc
        if not isinstance(parsed, Mapping):
            raise EmbeddingRequestError(
                f"embedding response schema error for {self.base_url}/embeddings "
                f"(batch {batch_number}): expected JSON object"
            )
        data = parsed.get("data")
        if not isinstance(data, list):
            raise EmbeddingRequestError(
                f"embedding response schema error for {self.base_url}/embeddings "
                f"(batch {batch_number}): missing data list"
            )
        try:
            sorted_data = sorted(data, key=lambda item: int(item.get("index", 0)))
            vectors = [[float(value) for value in item.get("embedding", [])] for item in sorted_data]
        except (AttributeError, TypeError, ValueError) as exc:
            raise EmbeddingRequestError(
                f"embedding response schema error for {self.base_url}/embeddings "
                f"(batch {batch_number}): invalid data item"
            ) from exc
        if len(vectors) != len(items):
            raise EmbeddingRequestError(
                f"embedding response count mismatch for {self.base_url}/embeddings "
                f"(batch {batch_number}): expected {len(items)}, got {len(vectors)}"
            )
        if not vectors or not vectors[0]:
            raise EmbeddingRequestError(
                f"embedding response is empty for {self.base_url}/embeddings (batch {batch_number})"
            )
        dimensions = len(vectors[0])
        for vector in vectors:
            if len(vector) != dimensions:
                raise EmbeddingRequestError(
                    f"embedding response dimension mismatch within batch {batch_number}: "
                    f"expected {dimensions}, got {len(vector)}"
                )
        if self.dimensions and dimensions != self.dimensions:
            raise EmbeddingRequestError(
                f"embedding dimension mismatch for {self.model}: expected {self.dimensions}, got {dimensions}"
            )
        self.dimensions = dimensions
        return [unit_vector(vector) for vector in vectors]

    def _post_embeddings(self, payload: bytes, batch_number: int) -> str:
        endpoint = f"{self.base_url}/embeddings"
        attempts = self.max_retries + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            request = urllib.request.Request(
                endpoint,
                data=payload,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    return response.read().decode("utf-8")
            except urllib.error.HTTPError as exc:
                last_error = exc
                if not retryable_http_status(exc.code) or attempt == attempts:
                    detail = http_error_detail(exc)
                    raise EmbeddingRequestError(
                        f"embedding HTTP error for {endpoint} (batch {batch_number}, attempt {attempt}/{attempts}): "
                        f"{exc.code} {exc.reason}{detail}"
                    ) from exc
            except urllib.error.URLError as exc:
                last_error = exc
                if attempt == attempts:
                    raise EmbeddingRequestError(
                        f"embedding request failed for {endpoint} (batch {batch_number}, attempt {attempt}/{attempts}): "
                        f"{exc.reason}"
                    ) from exc
            if attempt < attempts and self.retry_delay:
                time.sleep(self.retry_delay)
        raise EmbeddingRequestError(f"embedding request failed for {endpoint}: {last_error}")


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
            dimensions=optional_int(config.get("embedding_dimensions")),
            timeout=config_float(config, ("embedding_timeout", "timeout"), 30.0),
            batch_size=config_int(config, ("embedding_batch_size", "batch_size"), DEFAULT_EMBEDDING_BATCH_SIZE),
            max_retries=config_int(
                config,
                ("embedding_max_retries", "max_retries"),
                DEFAULT_EMBEDDING_MAX_RETRIES,
            ),
            retry_delay=config_float(
                config,
                ("embedding_retry_delay", "retry_delay"),
                DEFAULT_EMBEDDING_RETRY_DELAY,
            ),
        )
    return FakeEmbeddingModel(dimensions=config_int(config, ("fake_embedding_dimensions",), DEFAULT_DIMENSIONS))


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


def optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def config_int(config: Mapping[str, Any], keys: Sequence[str], default: int) -> int:
    for key in keys:
        value = config.get(key)
        if value not in (None, ""):
            return int(value)
    return default


def config_float(config: Mapping[str, Any], keys: Sequence[str], default: float) -> float:
    for key in keys:
        value = config.get(key)
        if value not in (None, ""):
            return float(value)
    return default


def model_fingerprint(provider: str, base_url: str, model: str) -> str:
    material = "\n".join([provider.strip(), base_url.rstrip("/"), model.strip()])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"sha256:{digest}"


def retryable_http_status(status: int) -> bool:
    return status in {408, 409, 425, 429} or 500 <= status <= 599


def http_error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        body = ""
    if not body:
        return ""
    return f": {sanitize_error_snippet(body)}"


def sanitize_error_snippet(text: str, limit: int = 300) -> str:
    compact = " ".join(text.split())
    compact = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-***", compact)
    if len(compact) > limit:
        return compact[:limit] + "..."
    return compact


def unit_vector(vector: Sequence[float]) -> List[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return [0.0 for _ in vector]
    return [value / norm for value in vector]


def _tokens(text: str) -> List[str]:
    normalized = text.lower()
    tokens = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", normalized)
    cjk_chars = [token for token in tokens if len(token) == 1 and "\u4e00" <= token <= "\u9fff"]
    cjk_bigrams = [a + b for a, b in zip(cjk_chars, cjk_chars[1:])]
    return tokens + cjk_bigrams
