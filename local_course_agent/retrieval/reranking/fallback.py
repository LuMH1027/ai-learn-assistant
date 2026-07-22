from __future__ import annotations

from typing import Dict, Sequence


class LocalRerankFallback:
    """No-op reranker because local scores are already attached upstream."""

    def rerank(self, *, query: str, documents: Sequence[Dict], top_n: int, stage: str) -> Sequence[Dict]:
        return list(documents)[:top_n]
