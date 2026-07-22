from __future__ import annotations

import re
from typing import Any, Dict, Mapping, Sequence

from local_course_agent.evaluation.quality.common import (
    KNOWN_LLM_STATUSES,
    KNOWN_SUMMARY_METHODS,
    as_list,
    quality_result,
    rate,
)


def evaluate_summary_payload(
    payload: Mapping[str, Any],
    *,
    expected_method: str | None = None,
    min_citation_quote_rate: float = 1.0,
    min_evidence_label_rate: float = 0.0,
) -> Dict[str, Any]:
    """Evaluate summary payload structure, fallback diagnostics, and evidence coverage."""

    checks: list[dict] = []

    def add(name: str, passed: bool, detail: str = "", observed: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail, "observed": observed})

    content = str(payload.get("content") or "")
    citations = as_list(payload.get("citations"))
    evidence_groups = as_list(payload.get("evidence_groups"))
    map_summaries = as_list(payload.get("map_summaries"))
    llm_status = str(payload.get("llm_status") or payload.get("status") or "")
    method = str(payload.get("summary_method") or "")
    fallback_reason = str(payload.get("fallback_reason") or "")

    for field in ("content", "citations", "llm_status", "summary_method"):
        add(f"summary_field:{field}", field in payload, observed=field in payload)
    add("summary_content_nonempty", bool(content.strip()) or llm_status == "empty", observed=len(content))
    add("summary_method_known", method in KNOWN_SUMMARY_METHODS, observed=method)
    add("summary_llm_status_known", llm_status in KNOWN_LLM_STATUSES, observed=llm_status)
    if expected_method is not None:
        add("summary_expected_method", method == expected_method, observed=method)

    citation_quote_count = sum(
        1
        for item in citations
        if isinstance(item, Mapping) and str(item.get("quote") or "").strip()
    )
    citation_quote_rate = rate(citation_quote_count, len(citations))
    add(
        "summary_citation_quote_coverage",
        citation_quote_rate >= min_citation_quote_rate,
        observed=citation_quote_rate,
    )

    evidence_labels = _summary_evidence_labels(evidence_groups)
    referenced_labels = _referenced_summary_labels(content, map_summaries)
    evidence_label_rate = rate(len(evidence_labels & referenced_labels), len(evidence_labels))
    if evidence_labels:
        add(
            "summary_evidence_label_coverage",
            evidence_label_rate >= min_evidence_label_rate,
            observed=evidence_label_rate,
        )

    if method == "map_reduce":
        add("summary_map_reduce_status_used", llm_status == "used", observed=llm_status)
        add("summary_map_reduce_evidence_groups", bool(evidence_groups), observed=len(evidence_groups))
        add("summary_map_reduce_map_outputs", bool(map_summaries), observed=len(map_summaries))
        add("summary_map_reduce_no_fallback_reason", not fallback_reason, observed=fallback_reason)
    elif method == "extractive" and citations:
        add(
            "summary_extractive_fallback_reason",
            bool(fallback_reason) or llm_status in {"skipped", "empty"},
            observed=fallback_reason,
        )
    elif method == "single_prompt":
        add("summary_single_prompt_citations", bool(citations), observed=len(citations))

    return quality_result(
        checks,
        metrics={
            "summary_method": method,
            "llm_status": llm_status,
            "citation_count": len(citations),
            "citation_quote_rate": citation_quote_rate,
            "evidence_group_count": len(evidence_groups),
            "evidence_label_rate": evidence_label_rate,
            "fallback_reason": fallback_reason,
        },
    )


def _summary_evidence_labels(evidence_groups: Sequence[Any]) -> set[str]:
    labels: set[str] = set()
    for group in evidence_groups:
        if not isinstance(group, Mapping):
            continue
        for item in as_list(group.get("evidence")):
            if isinstance(item, Mapping):
                label = str(item.get("label") or "").strip()
                if label:
                    labels.add(label)
    return labels


def _referenced_summary_labels(content: str, map_summaries: Sequence[Any]) -> set[str]:
    text_parts = [content]
    for item in map_summaries:
        if not isinstance(item, Mapping):
            continue
        text_parts.append(str(item.get("content") or ""))
        text_parts.extend(str(label) for label in as_list(item.get("evidence_labels")))
    return set(re.findall(r"\bS\d+\b", "\n".join(text_parts)))
