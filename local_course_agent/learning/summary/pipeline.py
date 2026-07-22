from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from local_course_agent.learning.summary.models import EvidenceGroup, SummaryEvidence
from local_course_agent.learning.summary.normalization import normalize_summary_evidence
from local_course_agent.learning.summary.serialization import evidence_group_to_dict, evidence_item_to_dict


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
