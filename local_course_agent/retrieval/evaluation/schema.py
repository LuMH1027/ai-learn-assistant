from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class RagEvalCase:
    id: str
    course_id: str
    question: str
    expected_files: List[str]
    min_quality: str = "partial"
    tags: List[str] = field(default_factory=list)
    expected_terms: List[str] = field(default_factory=list)
    forbidden_terms: List[str] = field(default_factory=list)
    min_answer_term_rate: float = 0.0
    max_unsupported_claims: Optional[int] = None

    @classmethod
    def from_dict(cls, payload: Dict) -> "RagEvalCase":
        expected_files = payload.get("expected_files") or payload.get("expected_reference_files") or []
        if isinstance(expected_files, str):
            expected_files = [expected_files]
        expected_terms = payload.get("expected_terms") or payload.get("expected_answer_terms") or []
        if isinstance(expected_terms, str):
            expected_terms = [expected_terms]
        forbidden_terms = payload.get("forbidden_terms") or []
        if isinstance(forbidden_terms, str):
            forbidden_terms = [forbidden_terms]
        max_unsupported = payload.get("max_unsupported_claims")
        return cls(
            id=str(payload.get("id") or payload["question"][:32]),
            course_id=str(payload["course_id"]),
            question=str(payload["question"]),
            expected_files=[str(item) for item in expected_files],
            min_quality=str(payload.get("min_quality", "partial")),
            tags=[str(item) for item in payload.get("tags", [])],
            expected_terms=[str(item) for item in expected_terms],
            forbidden_terms=[str(item) for item in forbidden_terms],
            min_answer_term_rate=float(payload.get("min_answer_term_rate", 0.0) or 0.0),
            max_unsupported_claims=None if max_unsupported in (None, "") else int(max_unsupported),
        )


__all__ = ["RagEvalCase"]
