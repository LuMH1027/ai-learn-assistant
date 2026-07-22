from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ClaimCheck:
    sentence: str
    labels: List[str]
    assertive: bool
    token_count: int
    max_overlap: float
    overlaps: Dict[str, float]
    supported: bool
    reason: str

    def as_dict(self) -> Dict:
        return {
            "sentence": self.sentence,
            "labels": self.labels,
            "assertive": self.assertive,
            "token_count": self.token_count,
            "max_overlap": round(self.max_overlap, 3),
            "overlaps": {label: round(score, 3) for label, score in self.overlaps.items()},
            "supported": self.supported,
            "reason": self.reason,
        }
