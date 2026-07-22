from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple


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


def build_summary_pipeline(
    chunks: Sequence[Dict],
    *,
    max_groups: int = 12,
    max_evidence_per_group: int = 5,
    max_text_chars: int = 900,
) -> Dict:
    evidence = normalize_summary_evidence(chunks, max_text_chars=max_text_chars)
    groups = group_evidence_by_section(
        evidence,
        max_groups=max_groups,
        max_evidence_per_group=max_evidence_per_group,
    )
    return {
        "evidence": [evidence_item_to_dict(item) for item in evidence],
        "groups": [evidence_group_to_dict(group) for group in groups],
    }


def normalize_summary_evidence(chunks: Sequence[Dict], *, max_text_chars: int = 900) -> List[SummaryEvidence]:
    evidence = []
    for index, chunk in enumerate(chunks, start=1):
        text = str(chunk.get("context_text") or chunk.get("quote") or chunk.get("text") or "").strip()
        if not text:
            continue
        evidence.append(
            SummaryEvidence(
                label=f"S{index}",
                file_id=str(chunk.get("file_id") or chunk.get("file_name") or "unknown"),
                file_name=str(chunk.get("file_name") or "未知文件"),
                file_path=str(chunk.get("file_path") or ""),
                section_title=str(chunk.get("section_title") or ""),
                material_type=str(chunk.get("material_type") or ""),
                page=chunk.get("page"),
                chunk_index=int(chunk.get("chunk_index") or index),
                text=compact_summary_text(text, max_text_chars),
            )
        )
    return evidence


def group_evidence_by_section(
    evidence: Sequence[SummaryEvidence],
    *,
    max_groups: int = 12,
    max_evidence_per_group: int = 5,
) -> List[EvidenceGroup]:
    ordered: Dict[Tuple[str, str], List[SummaryEvidence]] = {}
    for item in evidence:
        key = (item.file_id or item.file_name, item.section_title or "")
        ordered.setdefault(key, []).append(item)

    groups: List[EvidenceGroup] = []
    for index, ((file_id, section_title), items) in enumerate(ordered.items(), start=1):
        first = items[0]
        groups.append(
            EvidenceGroup(
                group_id=f"G{index}",
                file_id=file_id,
                file_name=first.file_name,
                section_title=section_title,
                material_type=first.material_type,
                evidence=tuple(items[:max_evidence_per_group]),
            )
        )
        if len(groups) >= max_groups:
            break
    return groups


def evidence_item_to_dict(item: SummaryEvidence) -> Dict:
    return {
        "label": item.label,
        "file_id": item.file_id,
        "file_name": item.file_name,
        "file_path": item.file_path,
        "section_title": item.section_title,
        "material_type": item.material_type,
        "page": item.page,
        "chunk_index": item.chunk_index,
        "text": item.text,
    }


def evidence_item_from_dict(item: Dict) -> SummaryEvidence:
    return SummaryEvidence(
        label=item["label"],
        file_id=item["file_id"],
        file_name=item["file_name"],
        file_path=item.get("file_path", ""),
        section_title=item.get("section_title", ""),
        material_type=item.get("material_type", ""),
        page=item.get("page"),
        chunk_index=item["chunk_index"],
        text=item["text"],
    )


def evidence_group_to_dict(group: EvidenceGroup) -> Dict:
    return {
        "group_id": group.group_id,
        "file_id": group.file_id,
        "file_name": group.file_name,
        "section_title": group.section_title,
        "material_type": group.material_type,
        "title": group.title,
        "evidence": [evidence_item_to_dict(item) for item in group.evidence],
    }


def evidence_group_from_dict(group: Dict) -> EvidenceGroup:
    return EvidenceGroup(
        group_id=group["group_id"],
        file_id=group["file_id"],
        file_name=group["file_name"],
        section_title=group.get("section_title", ""),
        material_type=group.get("material_type", ""),
        evidence=tuple(evidence_item_from_dict(item) for item in group.get("evidence", [])),
    )


def map_summary_to_dict(item: MapSummary) -> Dict:
    return {
        "group_id": item.group_id,
        "title": item.title,
        "file_name": item.file_name,
        "section_title": item.section_title,
        "content": item.content,
        "evidence_labels": list(item.evidence_labels),
    }


def map_summary_from_dict(item: Dict) -> MapSummary:
    return MapSummary(
        group_id=item["group_id"],
        title=item.get("title", ""),
        file_name=item.get("file_name", ""),
        section_title=item.get("section_title", ""),
        content=item.get("content", ""),
        evidence_labels=tuple(item.get("evidence_labels", [])),
    )


def summary_citation_from_chunk(chunk: Dict) -> Dict:
    page = chunk.get("page")
    location = f"第 {page} 页" if page else f"片段 {chunk.get('chunk_index', 0)}"
    section_title = str(chunk.get("section_title") or "")
    return {
        "file_id": chunk.get("file_id", ""),
        "file_name": chunk.get("file_name", "未知文件"),
        "file_path": chunk.get("file_path") or chunk.get("path", ""),
        "page": page,
        "chunk_index": chunk.get("chunk_index", 0),
        "location": location,
        "quote": chunk.get("context_text") or chunk.get("text", ""),
        "section_title": section_title,
        "material_type": chunk.get("material_type", ""),
    }


def compact_summary_text(text: str, max_chars: int) -> str:
    clean = " ".join(text.split())
    if len(clean) <= max_chars:
        return clean
    return clean[:max_chars].rstrip() + "..."
