from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List


SCHEMA_VERSION = 1


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
