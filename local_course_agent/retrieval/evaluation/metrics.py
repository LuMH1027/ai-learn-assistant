from __future__ import annotations

from pathlib import Path
from typing import List, Sequence


QUALITY_ORDER = {"none": 0, "partial": 1, "sufficient": 2}


def same_file(expected: str, returned: str) -> bool:
    expected_name = Path(expected).name
    returned_name = Path(returned).name
    return expected == returned or expected_name == returned_name


def rate(value: int, total: int) -> float:
    return round(value / total, 4) if total else 0.0


def answer_term_coverage(answer: str, expected_terms: Sequence[str]) -> tuple[List[str], List[str], float]:
    terms = [str(term) for term in expected_terms if str(term).strip()]
    if not terms:
        return [], [], 1.0
    found = [term for term in terms if term.lower() in answer.lower()]
    missing = [term for term in terms if term not in found]
    return found, missing, round(len(found) / len(terms), 4)


__all__ = ["QUALITY_ORDER", "answer_term_coverage", "rate", "same_file"]
