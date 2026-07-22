from __future__ import annotations

from local_course_agent.learning.summary.citations import summary_citation_from_chunk
from local_course_agent.learning.summary.models import EvidenceGroup, MapSummary, SummaryEvidence
from local_course_agent.learning.summary.normalization import compact_summary_text, normalize_summary_evidence
from local_course_agent.learning.summary.pipeline import build_summary_pipeline, group_evidence_by_section
from local_course_agent.learning.summary.serialization import (
    evidence_group_from_dict,
    evidence_group_to_dict,
    evidence_item_from_dict,
    evidence_item_to_dict,
    map_summary_from_dict,
    map_summary_to_dict,
)

__all__ = [
    "SummaryEvidence",
    "EvidenceGroup",
    "MapSummary",
    "build_summary_pipeline",
    "normalize_summary_evidence",
    "group_evidence_by_section",
    "evidence_item_to_dict",
    "evidence_item_from_dict",
    "evidence_group_to_dict",
    "evidence_group_from_dict",
    "map_summary_to_dict",
    "map_summary_from_dict",
    "summary_citation_from_chunk",
    "compact_summary_text",
]
