from __future__ import annotations

from typing import Iterable, List, Sequence

from local_course_agent.retrieval.embeddings.models import EmbeddingRequestError
from local_course_agent.retrieval.embeddings.openai_client import OpenAIEmbeddingHTTPClient
from local_course_agent.retrieval.embeddings.openai_payloads import (
    build_embedding_payload,
    parse_embedding_response,
)
from local_course_agent.retrieval.embeddings.utils import (
    DEFAULT_EMBEDDING_BATCH_SIZE,
    DEFAULT_EMBEDDING_MAX_RETRIES,
    DEFAULT_EMBEDDING_RETRY_DELAY,
    model_fingerprint,
    unit_vector,
)


class OpenAICompatibleEmbeddingModel:
    """OpenAI-compatible `/embeddings` provider for production vector retrieval."""

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
        self.endpoint = f"{self.base_url}/embeddings"
        self._client = OpenAIEmbeddingHTTPClient(
            endpoint=self.endpoint,
            api_key=self.api_key,
            timeout=self.timeout,
            max_retries=self.max_retries,
            retry_delay=self.retry_delay,
        )

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
        payload = build_embedding_payload(self.model, items)
        raw = self._post_embeddings(payload, batch_number=batch_number)
        parsed = self._parse_embedding_response(raw, len(items), batch_number)
        dimensions = len(parsed[0])
        if self.dimensions and dimensions != self.dimensions:
            raise EmbeddingRequestError(
                f"embedding dimension mismatch for {self.model}: expected {self.dimensions}, got {dimensions}"
            )
        self.dimensions = dimensions
        return [unit_vector(vector) for vector in parsed]

    def _post_embeddings(self, payload: bytes, batch_number: int) -> str:
        return self._client.post_embeddings(payload, batch_number=batch_number)

    def _parse_embedding_response(
        self,
        raw: str,
        expected_count: int,
        batch_number: int,
    ) -> List[List[float]]:
        return parse_embedding_response(
            raw,
            endpoint=self.endpoint,
            expected_count=expected_count,
            batch_number=batch_number,
        )
