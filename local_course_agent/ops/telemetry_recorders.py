from __future__ import annotations

from typing import Any, Mapping

from local_course_agent.ops.telemetry_core import TelemetryEvent, TelemetryRecorder
from local_course_agent.ops.telemetry_utils import (
    bool_from_payload,
    collect_trace_values,
    compact_attributes,
    first_present,
    number_from_payload,
    observe_if_number,
    sequence_from_payload,
    status_from_payload,
)


def record_index_result(
    recorder: TelemetryRecorder,
    payload: Mapping[str, Any],
    stage: str = "indexing",
) -> TelemetryEvent:
    """Record a normalized indexing result from an existing index-build payload."""

    status = status_from_payload(payload)
    attrs = compact_attributes(
        {
            "status": status,
            "course_id": first_present(payload, ("course_id", "course")),
            "schema_version": first_present(payload, ("schema_version", "index_schema_version")),
            "error": first_present(payload, ("error", "error_message", "message")),
        }
    )
    recorder.increment("index_jobs_total", stage=stage)
    recorder.increment(f"index_jobs_{'failed' if status == 'error' else 'succeeded'}", stage=stage)

    total_files = number_from_payload(payload, ("files_total", "total_files", "material_count"))
    indexed_files = number_from_payload(payload, ("files_indexed", "indexed_files", "processed_files"))
    skipped_files = number_from_payload(payload, ("files_skipped", "skipped_files"))
    failed_files = number_from_payload(payload, ("files_failed", "failed_files", "parse_failed"))
    chunk_count = number_from_payload(payload, ("chunks_total", "chunk_count", "chunks"))
    duration_ms = number_from_payload(payload, ("duration_ms", "elapsed_ms", "index_duration_ms"))

    observe_if_number(recorder, "index_files_total", total_files, stage)
    observe_if_number(recorder, "index_files_indexed", indexed_files, stage)
    observe_if_number(recorder, "index_files_skipped", skipped_files, stage)
    observe_if_number(recorder, "index_files_failed", failed_files, stage)
    observe_if_number(recorder, "index_chunks_total", chunk_count, stage)
    observe_if_number(recorder, "index_duration_ms", duration_ms, stage)

    if failed_files and failed_files > 0:
        recorder.increment("index_files_failed", amount=failed_files, stage=stage)
    if chunk_count and chunk_count > 0:
        recorder.increment("index_chunks_total", amount=chunk_count, stage=stage)

    attrs.update(
        compact_attributes(
            {
                "files_total": total_files,
                "files_indexed": indexed_files,
                "files_skipped": skipped_files,
                "files_failed": failed_files,
                "chunks_total": chunk_count,
                "duration_ms": duration_ms,
            }
        )
    )
    return recorder.event("index-result", stage=stage, attributes=attrs)


def record_retrieval_result(
    recorder: TelemetryRecorder,
    payload: Mapping[str, Any],
    stage: str = "retrieval",
) -> TelemetryEvent:
    """Record query-level retrieval diagnostics from a search or answer payload."""

    quality = first_present(payload, ("retrieval_quality", "quality", "evidence_quality"))
    sufficient = bool_from_payload(payload, ("sufficient", "is_sufficient", "evidence_sufficient"))
    citations = sequence_from_payload(payload, ("citations", "sources"))
    candidates = sequence_from_payload(payload, ("candidates", "results", "matches"))
    trace = sequence_from_payload(payload, ("retrieval_trace", "trace"))
    top_k = number_from_payload(payload, ("top_k", "topK", "k", "limit"))
    candidate_count = number_from_payload(payload, ("candidate_count", "candidates_count", "recalled_count"))
    reranked_count = number_from_payload(payload, ("reranked_count", "rerank_count"))
    duration_ms = number_from_payload(payload, ("duration_ms", "elapsed_ms", "retrieval_duration_ms"))

    if candidate_count is None and candidates is not None:
        candidate_count = float(len(candidates))
    if reranked_count is None and trace is not None:
        reranked_count = float(len(trace))
    citation_count = number_from_payload(payload, ("citation_count", "citations_count"))
    if citation_count is None and citations is not None:
        citation_count = float(len(citations))
    if top_k is None and trace is not None:
        top_k = float(len(trace))

    recorder.increment("retrieval_queries_total", stage=stage)
    if sufficient is False or quality in {"insufficient", "empty"}:
        recorder.increment("retrieval_queries_insufficient", stage=stage)
    else:
        recorder.increment("retrieval_queries_with_evidence", stage=stage)

    observe_if_number(recorder, "retrieval_top_k", top_k, stage)
    observe_if_number(recorder, "retrieval_candidate_count", candidate_count, stage)
    observe_if_number(recorder, "retrieval_reranked_count", reranked_count, stage)
    observe_if_number(recorder, "retrieval_citation_count", citation_count, stage)
    observe_if_number(recorder, "retrieval_duration_ms", duration_ms, stage)

    methods = collect_trace_values(trace, "method")
    files = collect_trace_values(trace, "file_name")
    attrs = compact_attributes(
        {
            "strategy": first_present(payload, ("strategy", "retrieval_strategy")),
            "quality": quality,
            "sufficient": sufficient,
            "top_k": top_k,
            "candidate_count": candidate_count,
            "reranked_count": reranked_count,
            "citation_count": citation_count,
            "duration_ms": duration_ms,
            "methods": methods,
            "files": files,
        }
    )
    return recorder.event("retrieval-result", stage=stage, attributes=attrs)


def record_llm_result(
    recorder: TelemetryRecorder,
    payload: Mapping[str, Any],
    stage: str = "llm",
) -> TelemetryEvent:
    """Record an LLM call result without requiring callers to use spans."""

    status = status_from_payload(payload)
    fallback_reason = first_present(payload, ("fallback_reason", "fallback", "fallback_to"))
    used_fallback = bool(fallback_reason) or bool(first_present(payload, ("used_fallback", "fallback_used")))
    duration_ms = number_from_payload(payload, ("duration_ms", "elapsed_ms", "latency_ms"))
    prompt_tokens = number_from_payload(payload, ("prompt_tokens", "input_tokens"))
    completion_tokens = number_from_payload(payload, ("completion_tokens", "output_tokens"))
    total_tokens = number_from_payload(payload, ("total_tokens", "tokens_total"))

    if total_tokens is None and (prompt_tokens is not None or completion_tokens is not None):
        total_tokens = float(prompt_tokens or 0) + float(completion_tokens or 0)

    recorder.increment("llm_calls_total", stage=stage)
    if status == "error":
        recorder.increment("llm_calls_failed", stage=stage)
    else:
        recorder.increment("llm_calls_succeeded", stage=stage)
    if used_fallback:
        recorder.increment("llm_calls_fallback", stage=stage)

    observe_if_number(recorder, "llm_duration_ms", duration_ms, stage)
    observe_if_number(recorder, "llm_prompt_tokens", prompt_tokens, stage)
    observe_if_number(recorder, "llm_completion_tokens", completion_tokens, stage)
    observe_if_number(recorder, "llm_total_tokens", total_tokens, stage)

    attrs = compact_attributes(
        {
            "status": status,
            "route": first_present(payload, ("route", "task", "purpose")),
            "model": first_present(payload, ("model", "model_name")),
            "provider": first_present(payload, ("provider", "base_url")),
            "duration_ms": duration_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "fallback_reason": fallback_reason,
            "error_type": first_present(payload, ("error_type",)),
            "error": first_present(payload, ("error", "error_message", "message")),
        }
    )
    return recorder.event("llm-result", stage=stage, attributes=attrs)


__all__ = [
    "record_index_result",
    "record_retrieval_result",
    "record_llm_result",
]
