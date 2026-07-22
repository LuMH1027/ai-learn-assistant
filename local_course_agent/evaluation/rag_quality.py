from __future__ import annotations

import re
from typing import Any, Dict, Mapping, Sequence


KNOWN_LLM_STATUSES = {
    "used",
    "fallback",
    "disabled",
    "skipped",
    "failed",
    "empty",
    "client_error",
    "summary_error",
}
KNOWN_WEB_STATUSES = {"used", "empty", "failed", "disabled", "skipped", "clarification"}
KNOWN_SUMMARY_METHODS = {"map_reduce", "single_prompt", "extractive"}
CHATFLOW_TRACE_LABELS = {"感知", "读取", "上下文", "检索", "联网", "回答", "记忆"}


def evaluate_chatflow_payload(
    payload: Mapping[str, Any],
    *,
    expect_contextual_query: bool | None = None,
    min_citations: int = 1,
    max_unsupported_claims: int | None = None,
) -> Dict[str, Any]:
    """Evaluate the structure emitted by the real ChatFlow orchestration."""

    checks: list[dict] = []

    def add(name: str, passed: bool, detail: str = "", observed: Any = None) -> None:
        checks.append({"name": name, "passed": bool(passed), "detail": detail, "observed": observed})

    citations = _list(payload.get("citations"))
    trace = _list(payload.get("trace"))
    retrieval_trace = payload.get("retrieval_trace") if isinstance(payload.get("retrieval_trace"), Mapping) else {}
    contextual = (
        retrieval_trace.get("contextual_query", {})
        if isinstance(retrieval_trace.get("contextual_query"), Mapping)
        else {}
    )
    citation_check = payload.get("citation_check") if isinstance(payload.get("citation_check"), Mapping) else {}
    telemetry = payload.get("telemetry") if isinstance(payload.get("telemetry"), Mapping) else {}

    for field in (
        "answer",
        "citations",
        "trace",
        "retrieval_trace",
        "citation_check",
        "llm_status",
        "web_search_status",
        "telemetry",
    ):
        add(f"chatflow_field:{field}", field in payload, observed=field in payload)

    add("chatflow_answer_nonempty", bool(str(payload.get("answer") or "").strip()))
    add("chatflow_min_citations", len(citations) >= min_citations, observed=len(citations))

    labels = [str(item.get("reference_label") or "").strip() for item in citations if isinstance(item, Mapping)]
    labels_are_unique = len(labels) == len(set(labels))
    labels_are_present = len(labels) == len(citations)
    add("chatflow_citation_labels_present", labels_are_present, observed=labels)
    add("chatflow_citation_labels_unique", labels_are_unique, observed=labels)

    llm_status = str(payload.get("llm_status") or "")
    web_status = str(payload.get("web_search_status") or "")
    add("chatflow_llm_status_known", llm_status in KNOWN_LLM_STATUSES, observed=llm_status)
    add("chatflow_web_status_known", web_status in KNOWN_WEB_STATUSES, observed=web_status)

    trace_labels = {str(item.get("label") or "") for item in trace if isinstance(item, Mapping)}
    missing_trace_labels = sorted(CHATFLOW_TRACE_LABELS - trace_labels)
    add("chatflow_trace_stage_coverage", not missing_trace_labels, observed=missing_trace_labels)

    add("chatflow_contextual_trace_present", bool(contextual), observed=contextual)
    if expect_contextual_query is not None:
        used = bool(contextual.get("used"))
        add("chatflow_contextual_expected_usage", used == expect_contextual_query, observed=used)
        if expect_contextual_query:
            add("chatflow_contextual_signals", bool(contextual.get("signals")), observed=contextual.get("signals"))
            add(
                "chatflow_contextual_turns",
                int(contextual.get("context_turns_used") or 0) > 0,
                observed=contextual.get("context_turns_used"),
            )
            add(
                "chatflow_contextual_rewrite",
                str(contextual.get("retrieval_query") or "") != str(contextual.get("original_query") or ""),
                observed=contextual.get("retrieval_query"),
            )

    stats = citation_check.get("stats") if isinstance(citation_check.get("stats"), Mapping) else {}
    unsupported_count = int(stats.get("unsupported_count") or 0)
    add("chatflow_citation_check_stats", bool(stats), observed=stats)
    if max_unsupported_claims is not None:
        add(
            "chatflow_unsupported_claim_budget",
            unsupported_count <= max_unsupported_claims,
            observed=unsupported_count,
        )

    telemetry_summary = telemetry.get("summary") if isinstance(telemetry.get("summary"), Mapping) else {}
    missing_telemetry = sorted({"retrieval", "web", "llm", "citation_check"} - set(telemetry_summary))
    add("chatflow_telemetry_stage_coverage", not missing_telemetry, observed=missing_telemetry)

    return _quality_result(
        checks,
        metrics={
            "citation_count": len(citations),
            "unsupported_claim_count": unsupported_count,
            "llm_status": llm_status,
            "web_search_status": web_status,
            "contextual_query_used": bool(contextual.get("used")),
        },
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
    citations = _list(payload.get("citations"))
    evidence_groups = _list(payload.get("evidence_groups"))
    map_summaries = _list(payload.get("map_summaries"))
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
    citation_quote_rate = _rate(citation_quote_count, len(citations))
    add(
        "summary_citation_quote_coverage",
        citation_quote_rate >= min_citation_quote_rate,
        observed=citation_quote_rate,
    )

    evidence_labels = _summary_evidence_labels(evidence_groups)
    referenced_labels = _referenced_summary_labels(content, map_summaries)
    evidence_label_rate = _rate(len(evidence_labels & referenced_labels), len(evidence_labels))
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

    return _quality_result(
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


def summarize_quality_results(results: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    passed = sum(1 for item in results if item.get("passed"))
    failed_checks: Dict[str, int] = {}
    for item in results:
        for check in item.get("checks", []):
            if isinstance(check, Mapping) and not check.get("passed"):
                name = str(check.get("name") or "unknown")
                failed_checks[name] = failed_checks.get(name, 0) + 1
    return {
        "total_cases": total,
        "passed_cases": passed,
        "pass_rate": _rate(passed, total),
        "failed_checks": failed_checks,
    }


def _quality_result(checks: Sequence[Mapping[str, Any]], metrics: Mapping[str, Any]) -> Dict[str, Any]:
    failed = [check for check in checks if not check.get("passed")]
    return {
        "passed": not failed,
        "checks": list(checks),
        "failed_checks": failed,
        "metrics": dict(metrics),
    }


def _list(value: Any) -> list:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def _rate(value: int, total: int) -> float:
    return round(value / total, 4) if total else 0.0


def _summary_evidence_labels(evidence_groups: Sequence[Any]) -> set[str]:
    labels: set[str] = set()
    for group in evidence_groups:
        if not isinstance(group, Mapping):
            continue
        for item in _list(group.get("evidence")):
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
        text_parts.extend(str(label) for label in _list(item.get("evidence_labels")))
    return set(re.findall(r"\bS\d+\b", "\n".join(text_parts)))

