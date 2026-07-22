from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from typing import Iterable, List, Mapping, Sequence

from local_course_agent.retrieval.embedding_models import EmbeddingRequestError
from local_course_agent.retrieval.embedding_utils import (
    DEFAULT_DIMENSIONS,
    DEFAULT_EMBEDDING_BATCH_SIZE,
    DEFAULT_EMBEDDING_MAX_RETRIES,
    DEFAULT_EMBEDDING_RETRY_DELAY,
    http_error_detail,
    model_fingerprint,
    retryable_http_status,
    tokens,
    unit_vector,
)


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
        for token in tokens(text):
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
        parsed = self._parse_embedding_response(raw, len(items), batch_number)
        dimensions = len(parsed[0])
        if self.dimensions and dimensions != self.dimensions:
            raise EmbeddingRequestError(
                f"embedding dimension mismatch for {self.model}: expected {self.dimensions}, got {dimensions}"
            )
        self.dimensions = dimensions
        return [unit_vector(vector) for vector in parsed]

    def _parse_embedding_response(
        self,
        raw: str,
        expected_count: int,
        batch_number: int,
    ) -> List[List[float]]:
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
        if len(vectors) != expected_count:
            raise EmbeddingRequestError(
                f"embedding response count mismatch for {self.base_url}/embeddings "
                f"(batch {batch_number}): expected {expected_count}, got {len(vectors)}"
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
        return vectors

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
