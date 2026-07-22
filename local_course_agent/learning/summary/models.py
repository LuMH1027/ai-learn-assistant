from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass(frozen=True)
class SummaryEvidence:
    label: str
    file_id: str
    file_name: str
    file_path: str
    section_title: str
    material_type: str
    page: Optional[int]
    chunk_index: int
    text: str


@dataclass(frozen=True)
class EvidenceGroup:
    group_id: str
    file_id: str
    file_name: str
    section_title: str
    material_type: str
    evidence: Tuple[SummaryEvidence, ...]

    @property
    def title(self) -> str:
        return self.section_title or self.file_name or "未命名章节"


@dataclass(frozen=True)
class MapSummary:
    group_id: str
    title: str
    file_name: str
    section_title: str
    content: str
    evidence_labels: Tuple[str, ...]
