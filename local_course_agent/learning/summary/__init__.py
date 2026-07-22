from __future__ import annotations

from local_course_agent.learning.summary.prompts import (
    build_map_prompt,
    build_reduce_prompt,
    format_evidence_block,
    format_map_summary_block,
)
from local_course_agent.learning.summary.runner import (
    EMPTY_SUMMARY_MESSAGE,
    CourseSummaryKnowledgeBase,
    SummaryLLMClient,
    fallback_reason_for_status,
    generate_map_reduce_course_summary,
    map_reduce_fallback_payload,
    run_map_reduce_summary,
)
from local_course_agent.learning.summary.schema import (
    EvidenceGroup,
    MapSummary,
    SummaryEvidence,
    build_summary_pipeline,
    compact_summary_text,
    evidence_group_from_dict,
    evidence_group_to_dict,
    evidence_item_from_dict,
    evidence_item_to_dict,
    group_evidence_by_section,
    map_summary_from_dict,
    map_summary_to_dict,
    normalize_summary_evidence,
    summary_citation_from_chunk,
)

# Compatibility aliases for older tests/tools that reached into the previous
# single-file implementation.
_compact_text = compact_summary_text
_evidence_from_dict = evidence_item_from_dict
_fallback_reason_for_status = fallback_reason_for_status
_format_evidence_block = format_evidence_block
_format_map_summary_block = format_map_summary_block
_map_reduce_fallback_payload = map_reduce_fallback_payload

__all__ = [
    "EMPTY_SUMMARY_MESSAGE",
    "CourseSummaryKnowledgeBase",
    "SummaryLLMClient",
    "SummaryEvidence",
    "EvidenceGroup",
    "MapSummary",
    "build_summary_pipeline",
    "normalize_summary_evidence",
    "group_evidence_by_section",
    "build_map_prompt",
    "build_reduce_prompt",
    "run_map_reduce_summary",
    "generate_map_reduce_course_summary",
    "evidence_item_to_dict",
    "evidence_item_from_dict",
    "evidence_group_to_dict",
    "evidence_group_from_dict",
    "map_summary_to_dict",
    "map_summary_from_dict",
    "summary_citation_from_chunk",
    "format_evidence_block",
    "format_map_summary_block",
    "compact_summary_text",
    "map_reduce_fallback_payload",
    "fallback_reason_for_status",
]
