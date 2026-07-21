from __future__ import annotations

import json
import time
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Sequence


Clock = Callable[[], float]


@dataclass
class TelemetryEvent:
    name: str
    stage: str
    timestamp: float
    attributes: Dict = field(default_factory=dict)


@dataclass
class TelemetrySpan:
    name: str
    stage: str
    started_at: float
    ended_at: Optional[float] = None
    duration_ms: Optional[float] = None
    status: str = "running"
    attributes: Dict = field(default_factory=dict)


@dataclass
class TelemetryCounter:
    name: str
    stage: str
    value: float = 0.0


@dataclass
class TelemetryObservation:
    name: str
    stage: str
    value: float
    timestamp: float
    attributes: Dict = field(default_factory=dict)


class TelemetryRecorder:
    """In-memory telemetry buffer for request-local or job-local diagnostics."""

    def __init__(self, clock: Optional[Clock] = None):
        self._clock = clock or time.monotonic
        self.events: List[TelemetryEvent] = []
        self.spans: List[TelemetrySpan] = []
        self.counters: Dict[str, TelemetryCounter] = {}
        self.observations: List[TelemetryObservation] = []

    def event(self, name: str, stage: str = "general", attributes: Optional[Mapping] = None) -> TelemetryEvent:
        event = TelemetryEvent(
            name=_require_name(name, "event name"),
            stage=_normalize_stage(stage),
            timestamp=self._clock(),
            attributes=dict(attributes or {}),
        )
        self.events.append(event)
        return event

    def increment(self, name: str, amount: float = 1.0, stage: str = "general") -> TelemetryCounter:
        if amount < 0:
            raise ValueError("counter amount must be non-negative")
        key = _counter_key(stage, name)
        counter = self.counters.get(key)
        if counter is None:
            counter = TelemetryCounter(name=_require_name(name, "counter name"), stage=_normalize_stage(stage))
            self.counters[key] = counter
        counter.value += float(amount)
        return counter

    def observe(
        self,
        name: str,
        value: float,
        stage: str = "general",
        attributes: Optional[Mapping] = None,
    ) -> TelemetryObservation:
        observation = TelemetryObservation(
            name=_require_name(name, "observation name"),
            stage=_normalize_stage(stage),
            value=float(value),
            timestamp=self._clock(),
            attributes=dict(attributes or {}),
        )
        self.observations.append(observation)
        return observation

    def span(self, name: str, stage: str = "general", attributes: Optional[Mapping] = None) -> "_SpanContext":
        return _SpanContext(
            recorder=self,
            span=TelemetrySpan(
                name=_require_name(name, "span name"),
                stage=_normalize_stage(stage),
                started_at=self._clock(),
                attributes=dict(attributes or {}),
            ),
        )

    def to_dict(self) -> Dict:
        return {
            "events": [asdict(event) for event in self.events],
            "spans": [asdict(span) for span in self.spans],
            "counters": [asdict(counter) for counter in self.counters.values()],
            "observations": [asdict(observation) for observation in self.observations],
            "summary": self.summary_by_stage(),
        }

    def to_json(self, indent: Optional[int] = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def summary_by_stage(self) -> Dict[str, Dict]:
        stages = sorted(
            {
                event.stage
                for event in self.events
            }
            | {span.stage for span in self.spans}
            | {counter.stage for counter in self.counters.values()}
            | {observation.stage for observation in self.observations}
        )
        return {stage: self._summarize_stage(stage) for stage in stages}

    def _summarize_stage(self, stage: str) -> Dict:
        spans = [span for span in self.spans if span.stage == stage]
        events = [event for event in self.events if event.stage == stage]
        counters = {
            counter.name: counter.value
            for counter in self.counters.values()
            if counter.stage == stage
        }
        observations = [observation for observation in self.observations if observation.stage == stage]
        return {
            "event_count": len(events),
            "span_count": len(spans),
            "error_span_count": sum(1 for span in spans if span.status == "error"),
            "duration_ms": _duration_summary([span.duration_ms for span in spans if span.duration_ms is not None]),
            "counters": counters,
            "observations": _observation_summary(observations),
        }

    def _finish_span(self, span: TelemetrySpan, status: str, attributes: Optional[Mapping] = None) -> TelemetrySpan:
        ended_at = self._clock()
        span.ended_at = ended_at
        span.duration_ms = round(max(0.0, ended_at - span.started_at) * 1000, 3)
        span.status = status
        if attributes:
            span.attributes.update(dict(attributes))
        self.spans.append(span)
        return span


def record_index_result(
    recorder: TelemetryRecorder,
    payload: Mapping[str, Any],
    stage: str = "indexing",
) -> TelemetryEvent:
    """Record a normalized indexing result from an existing index-build payload."""

    status = _status_from_payload(payload)
    attrs = _compact_attributes(
        {
            "status": status,
            "course_id": _first_present(payload, ("course_id", "course")),
            "schema_version": _first_present(payload, ("schema_version", "index_schema_version")),
            "error": _first_present(payload, ("error", "error_message", "message")),
        }
    )
    recorder.increment("index_jobs_total", stage=stage)
    recorder.increment(f"index_jobs_{'failed' if status == 'error' else 'succeeded'}", stage=stage)

    total_files = _number_from_payload(payload, ("files_total", "total_files", "material_count"))
    indexed_files = _number_from_payload(payload, ("files_indexed", "indexed_files", "processed_files"))
    skipped_files = _number_from_payload(payload, ("files_skipped", "skipped_files"))
    failed_files = _number_from_payload(payload, ("files_failed", "failed_files", "parse_failed"))
    chunk_count = _number_from_payload(payload, ("chunks_total", "chunk_count", "chunks"))
    duration_ms = _number_from_payload(payload, ("duration_ms", "elapsed_ms", "index_duration_ms"))

    _observe_if_number(recorder, "index_files_total", total_files, stage)
    _observe_if_number(recorder, "index_files_indexed", indexed_files, stage)
    _observe_if_number(recorder, "index_files_skipped", skipped_files, stage)
    _observe_if_number(recorder, "index_files_failed", failed_files, stage)
    _observe_if_number(recorder, "index_chunks_total", chunk_count, stage)
    _observe_if_number(recorder, "index_duration_ms", duration_ms, stage)

    if failed_files and failed_files > 0:
        recorder.increment("index_files_failed", amount=failed_files, stage=stage)
    if chunk_count and chunk_count > 0:
        recorder.increment("index_chunks_total", amount=chunk_count, stage=stage)

    attrs.update(
        _compact_attributes(
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

    quality = _first_present(payload, ("retrieval_quality", "quality", "evidence_quality"))
    sufficient = _bool_from_payload(payload, ("sufficient", "is_sufficient", "evidence_sufficient"))
    citations = _sequence_from_payload(payload, ("citations", "sources"))
    candidates = _sequence_from_payload(payload, ("candidates", "results", "matches"))
    trace = _sequence_from_payload(payload, ("retrieval_trace", "trace"))
    top_k = _number_from_payload(payload, ("top_k", "topK", "k", "limit"))
    candidate_count = _number_from_payload(payload, ("candidate_count", "candidates_count", "recalled_count"))
    reranked_count = _number_from_payload(payload, ("reranked_count", "rerank_count"))
    duration_ms = _number_from_payload(payload, ("duration_ms", "elapsed_ms", "retrieval_duration_ms"))

    if candidate_count is None and candidates is not None:
        candidate_count = float(len(candidates))
    if reranked_count is None and trace is not None:
        reranked_count = float(len(trace))
    citation_count = _number_from_payload(payload, ("citation_count", "citations_count"))
    if citation_count is None and citations is not None:
        citation_count = float(len(citations))
    if top_k is None and trace is not None:
        top_k = float(len(trace))

    recorder.increment("retrieval_queries_total", stage=stage)
    if sufficient is False or quality in {"insufficient", "empty"}:
        recorder.increment("retrieval_queries_insufficient", stage=stage)
    else:
        recorder.increment("retrieval_queries_with_evidence", stage=stage)

    _observe_if_number(recorder, "retrieval_top_k", top_k, stage)
    _observe_if_number(recorder, "retrieval_candidate_count", candidate_count, stage)
    _observe_if_number(recorder, "retrieval_reranked_count", reranked_count, stage)
    _observe_if_number(recorder, "retrieval_citation_count", citation_count, stage)
    _observe_if_number(recorder, "retrieval_duration_ms", duration_ms, stage)

    methods = _collect_trace_values(trace, "method")
    files = _collect_trace_values(trace, "file_name")
    attrs = _compact_attributes(
        {
            "strategy": _first_present(payload, ("strategy", "retrieval_strategy")),
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

    status = _status_from_payload(payload)
    fallback_reason = _first_present(payload, ("fallback_reason", "fallback", "fallback_to"))
    used_fallback = bool(fallback_reason) or bool(_first_present(payload, ("used_fallback", "fallback_used")))
    duration_ms = _number_from_payload(payload, ("duration_ms", "elapsed_ms", "latency_ms"))
    prompt_tokens = _number_from_payload(payload, ("prompt_tokens", "input_tokens"))
    completion_tokens = _number_from_payload(payload, ("completion_tokens", "output_tokens"))
    total_tokens = _number_from_payload(payload, ("total_tokens", "tokens_total"))

    if total_tokens is None and (prompt_tokens is not None or completion_tokens is not None):
        total_tokens = float(prompt_tokens or 0) + float(completion_tokens or 0)

    recorder.increment("llm_calls_total", stage=stage)
    if status == "error":
        recorder.increment("llm_calls_failed", stage=stage)
    else:
        recorder.increment("llm_calls_succeeded", stage=stage)
    if used_fallback:
        recorder.increment("llm_calls_fallback", stage=stage)

    _observe_if_number(recorder, "llm_duration_ms", duration_ms, stage)
    _observe_if_number(recorder, "llm_prompt_tokens", prompt_tokens, stage)
    _observe_if_number(recorder, "llm_completion_tokens", completion_tokens, stage)
    _observe_if_number(recorder, "llm_total_tokens", total_tokens, stage)

    attrs = _compact_attributes(
        {
            "status": status,
            "route": _first_present(payload, ("route", "task", "purpose")),
            "model": _first_present(payload, ("model", "model_name")),
            "provider": _first_present(payload, ("provider", "base_url")),
            "duration_ms": duration_ms,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
            "fallback_reason": fallback_reason,
            "error_type": _first_present(payload, ("error_type",)),
            "error": _first_present(payload, ("error", "error_message", "message")),
        }
    )
    return recorder.event("llm-result", stage=stage, attributes=attrs)


class _SpanContext(AbstractContextManager):
    def __init__(self, recorder: TelemetryRecorder, span: TelemetrySpan):
        self._recorder = recorder
        self.span = span
        self._finished = False

    def __enter__(self) -> TelemetrySpan:
        return self.span

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is None:
            self.finish("ok")
            return False
        self.finish(
            "error",
            {
                "error_type": exc_type.__name__,
                "error_message": str(exc),
            },
        )
        return False

    def finish(self, status: str = "ok", attributes: Optional[Mapping] = None) -> TelemetrySpan:
        if self._finished:
            return self.span
        if status not in {"ok", "error"}:
            raise ValueError("span status must be 'ok' or 'error'")
        self._finished = True
        return self._recorder._finish_span(self.span, status, attributes)


def _duration_summary(values: List[float]) -> Dict:
    if not values:
        return {"count": 0, "total": 0.0, "min": None, "max": None, "avg": None}
    total = sum(values)
    return {
        "count": len(values),
        "total": round(total, 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
        "avg": round(total / len(values), 3),
    }


def _observation_summary(observations: List[TelemetryObservation]) -> Dict[str, Dict]:
    grouped: Dict[str, List[float]] = {}
    for observation in observations:
        grouped.setdefault(observation.name, []).append(observation.value)
    return {name: _numeric_summary(values) for name, values in sorted(grouped.items())}


def _numeric_summary(values: List[float]) -> Dict:
    if not values:
        return {"count": 0, "min": None, "max": None, "avg": None, "distribution": {}}
    total = sum(values)
    distribution: Dict[str, int] = {}
    for value in values:
        bucket = str(int(value)) if value.is_integer() else str(value)
        distribution[bucket] = distribution.get(bucket, 0) + 1
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "avg": round(total / len(values), 3),
        "distribution": dict(sorted(distribution.items(), key=lambda item: float(item[0]))),
    }


def _counter_key(stage: str, name: str) -> str:
    return f"{_normalize_stage(stage)}:{_require_name(name, 'counter name')}"


def _normalize_stage(stage: str) -> str:
    return str(stage or "general")


def _require_name(name: str, label: str) -> str:
    normalized = str(name or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def _first_present(payload: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


def _number_from_payload(payload: Mapping[str, Any], keys: Iterable[str]) -> Optional[float]:
    value = _first_present(payload, keys)
    if value is None:
        return None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return float(len(value))
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bool_from_payload(payload: Mapping[str, Any], keys: Iterable[str]) -> Optional[bool]:
    value = _first_present(payload, keys)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1", "ok", "sufficient"}:
            return True
        if normalized in {"false", "no", "0", "insufficient", "empty"}:
            return False
    return bool(value)


def _sequence_from_payload(payload: Mapping[str, Any], keys: Iterable[str]) -> Optional[Sequence]:
    value = _first_present(payload, keys)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return None


def _status_from_payload(payload: Mapping[str, Any]) -> str:
    status = _first_present(payload, ("status", "llm_status"))
    if isinstance(status, str):
        normalized = status.strip().lower()
        if normalized in {"error", "failed", "failure", "timeout"}:
            return "error"
        if normalized in {"ok", "success", "succeeded", "completed", "ready"}:
            return "ok"
    if _first_present(payload, ("error", "error_message")):
        return "error"
    return "ok"


def _observe_if_number(recorder: TelemetryRecorder, name: str, value: Optional[float], stage: str) -> None:
    if value is not None:
        recorder.observe(name, value, stage=stage)


def _compact_attributes(attributes: Mapping[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in attributes.items() if value is not None and value != []}


def _collect_trace_values(trace: Optional[Sequence], key: str, limit: int = 8) -> List[Any]:
    if not trace:
        return []
    values: List[Any] = []
    seen = set()
    for item in trace:
        if not isinstance(item, Mapping):
            continue
        value = item.get(key)
        if value is None or value in seen:
            continue
        seen.add(value)
        values.append(value)
        if len(values) >= limit:
            break
    return values
