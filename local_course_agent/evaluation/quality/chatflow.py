from __future__ import annotations

from typing import Any, Dict, Mapping

from local_course_agent.evaluation.quality.common import (
    KNOWN_LLM_STATUSES,
    KNOWN_WEB_STATUSES,
    as_list,
    quality_result,
)


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

    citations = as_list(payload.get("citations"))
    trace = as_list(payload.get("trace"))
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

    return quality_result(
        checks,
        metrics={
            "citation_count": len(citations),
            "unsupported_claim_count": unsupported_count,
            "llm_status": llm_status,
            "web_search_status": web_status,
            "contextual_query_used": bool(contextual.get("used")),
        },
    )
