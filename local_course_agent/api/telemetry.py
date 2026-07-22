from __future__ import annotations

from collections.abc import Mapping, Sequence

from local_course_agent.ops.telemetry import (
    TelemetryRecorder,
    record_llm_result,
    record_retrieval_result,
)


def compact_retrieval_telemetry(result: Mapping) -> dict:
    trace = result.get("retrieval_trace", {})
    selected = trace.get("selected", []) if isinstance(trace, Mapping) else []
    if not isinstance(selected, Sequence) or isinstance(selected, (str, bytes, bytearray)):
        selected = []
    citations = result.get("citations", [])
    if not isinstance(citations, Sequence) or isinstance(citations, (str, bytes, bytearray)):
        citations = []
    quality = result.get("retrieval_quality", "none")
    return {
        "retrieval_quality": quality,
        "sufficient": quality == "sufficient",
        "citations": list(citations),
        "retrieval_trace": list(selected),
        "candidate_count": len(selected),
        "reranked_count": len(selected),
        "citation_count": len(citations),
        "top_k": len(selected),
    }


def record_chat_retrieval_result(telemetry: TelemetryRecorder, result: Mapping) -> None:
    record_retrieval_result(telemetry, compact_retrieval_telemetry(result))


def record_chat_llm_result(
    telemetry: TelemetryRecorder,
    *,
    llm_status: str,
    route: str = "chat_answer",
    fallback_reason: str | None = None,
) -> None:
    record_llm_result(
        telemetry,
        {
            "llm_status": llm_status,
            "route": route,
            "fallback_reason": fallback_reason,
        },
    )


def record_web_result(
    telemetry: TelemetryRecorder,
    status: str,
    sources: Sequence[Mapping],
    *,
    allow_web: bool,
) -> None:
    source_count = len(sources or [])
    telemetry.increment("web_search_checks_total", stage="web")
    if status == "used":
        telemetry.increment("web_search_used", stage="web")
    elif status == "failed":
        telemetry.increment("web_search_failed", stage="web")
    else:
        telemetry.increment(f"web_search_{status}", stage="web")
    telemetry.observe("web_source_count", source_count, stage="web")
    telemetry.event(
        "web-result",
        stage="web",
        attributes={"status": status, "source_count": source_count, "allow_web": allow_web},
    )


def record_citation_check_result(telemetry: TelemetryRecorder, citation_check: Mapping) -> None:
    stats = citation_check.get("stats", {}) if isinstance(citation_check, Mapping) else {}
    unsupported_count = int(stats.get("unsupported_count") or 0)
    supported = bool(citation_check.get("supported")) if isinstance(citation_check, Mapping) else False
    telemetry.increment("citation_checks_total", stage="citation_check")
    if supported:
        telemetry.increment("citation_checks_supported", stage="citation_check")
    else:
        telemetry.increment("citation_checks_unsupported", stage="citation_check")
    telemetry.observe("unsupported_claim_count", unsupported_count, stage="citation_check")
    telemetry.event(
        "citation-check-result",
        stage="citation_check",
        attributes={"supported": supported, "unsupported_count": unsupported_count},
    )


def compact_telemetry_payload(telemetry: TelemetryRecorder) -> dict:
    payload = telemetry.to_dict()
    return {
        "summary": payload["summary"],
        "spans": [
            {
                "name": span["name"],
                "stage": span["stage"],
                "status": span["status"],
                "duration_ms": span["duration_ms"],
            }
            for span in payload["spans"]
        ],
        "events": [
            {
                "name": event["name"],
                "stage": event["stage"],
                "attributes": event.get("attributes", {}),
            }
            for event in payload["events"]
        ],
    }
