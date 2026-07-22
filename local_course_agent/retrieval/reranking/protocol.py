from __future__ import annotations

from typing import Dict, Protocol, Sequence, runtime_checkable


@runtime_checkable
class CandidateReranker(Protocol):
    """Optional cross-encoder reranker hook for RAG candidates."""

    def rerank(self, *, query: str, documents: Sequence[Dict], top_n: int, stage: str) -> Sequence[Dict]:
        ...
