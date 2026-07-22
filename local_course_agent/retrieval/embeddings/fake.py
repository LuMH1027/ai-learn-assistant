from __future__ import annotations

import hashlib
from typing import Iterable, List

from local_course_agent.retrieval.embeddings.utils import (
    DEFAULT_DIMENSIONS,
    model_fingerprint,
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
