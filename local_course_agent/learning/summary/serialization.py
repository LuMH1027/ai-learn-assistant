from __future__ import annotations

from typing import Dict

from local_course_agent.learning.summary.models import EvidenceGroup, MapSummary, SummaryEvidence


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
