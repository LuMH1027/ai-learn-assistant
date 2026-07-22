# Telemetry module

`local_course_agent.ops.telemetry` is the compatibility entry point for a small
in-memory telemetry buffer used by RAG and course-processing diagnostics. The
recorder itself is intentionally pure: no background thread, no file writes, and
no third-party dependency. Runtime callers decide whether to return, persist, or
aggregate the compact payload.

The implementation is split by responsibility:

- `ops/telemetry/core.py`: dataclasses, `TelemetryRecorder`, span lifecycle, and
  serialization.
- `ops/telemetry/utils.py`: stage/name normalization, payload coercion, and
  numeric summary helpers.
- `ops/telemetry/recorders.py`: domain-level `record_index_result`,
  `record_retrieval_result`, and `record_llm_result` helpers.
- `ops/telemetry/__init__.py`: stable re-export facade for existing imports.

The chat API now creates a request-local recorder through
`local_course_agent.api.telemetry`. Chat responses include a compact
`telemetry` field with stage summaries, spans, and sanitized events for
attachment indexing, retrieval, optional web search, LLM generation, and
citation checking.

## Current API

```python
from local_course_agent.ops.telemetry import (
    TelemetryRecorder,
    record_index_result,
    record_llm_result,
    record_retrieval_result,
)

telemetry = TelemetryRecorder()

with telemetry.span("build-index", stage="indexing", attributes={"course_id": "os"}):
    ...

telemetry.event("parse-failed", stage="parsing", attributes={"file": "scan.pdf"})
telemetry.increment("files_failed", stage="parsing")
telemetry.observe("retrieval_top_k", 8, stage="retrieval")

record_index_result(telemetry, {"course_id": "os", "indexed_files": 3, "chunk_count": 42})
record_retrieval_result(telemetry, {"strategy": "hybrid", "citations": [...], "retrieval_trace": [...]})
record_llm_result(telemetry, {"route": "answer", "model": "gpt-test", "duration_ms": 850})

payload = telemetry.to_dict()
json_text = telemetry.to_json()
summary = telemetry.summary_by_stage()
```

## Data captured

- Spans: operation name, stage, start/end timestamps, duration in milliseconds,
  status, and attributes. Exceptions mark the span as `error` and keep the
  exception type/message in attributes.
- Events: timestamped point-in-time facts with optional attributes.
- Counters: additive numeric metrics grouped by `stage + name`.
- Observations: numeric samples with per-stage summaries and value
  distributions. This is meant for topK sizes, candidate counts, prompt token
  estimates, and similar diagnostics.

## Result helpers

The module also provides three low-friction helpers for runtime integration
points. They accept existing result payload dictionaries, normalize common field
names, then write counters, observations, and one event.

### `record_index_result`

Use after a course index build completes or fails:

```python
record_index_result(
    telemetry,
    {
        "course_id": "os",
        "status": "ok",
        "total_files": 5,
        "indexed_files": 4,
        "skipped_files": 1,
        "chunk_count": 96,
        "duration_ms": 1200,
    },
)
```

Counters:

- `index_jobs_total`
- `index_jobs_succeeded` / `index_jobs_failed`
- `index_files_failed` when failures are reported
- `index_chunks_total` when chunks are reported

Observations:

- `index_files_total`
- `index_files_indexed`
- `index_files_skipped`
- `index_files_failed`
- `index_chunks_total`
- `index_duration_ms`

Event:

- `index-result` with course ID, status, schema version, file counts, chunk
  count, duration, and error text when present.

Accepted aliases include `files_total`, `total_files`, `material_count`,
`files_indexed`, `indexed_files`, `processed_files`, `chunks_total`,
`chunk_count`, `duration_ms`, and `elapsed_ms`.

### `record_retrieval_result`

Use after search, rerank, or answer retrieval context assembly:

```python
record_retrieval_result(
    telemetry,
    {
        "strategy": "hybrid",
        "retrieval_quality": "partial",
        "sufficient": False,
        "citations": [{"id": "L1"}],
        "results": [{"chunk_id": "c1"}],
        "retrieval_trace": [{"method": "bm25", "file_name": "chapter.md"}],
        "duration_ms": 33.5,
    },
)
```

Counters:

- `retrieval_queries_total`
- `retrieval_queries_with_evidence`
- `retrieval_queries_insufficient`

Observations:

- `retrieval_top_k`
- `retrieval_candidate_count`
- `retrieval_reranked_count`
- `retrieval_citation_count`
- `retrieval_duration_ms`

Event:

- `retrieval-result` with strategy, quality, sufficiency, counts, duration,
  matched methods, and touched files.

When explicit counts are missing, the helper derives counts from `citations`,
`sources`, `candidates`, `results`, `matches`, and `retrieval_trace` lists.

### `record_llm_result`

Use after an LLM answer, summary, rewrite, or rerank call:

```python
record_llm_result(
    telemetry,
    {
        "status": "success",
        "route": "answer",
        "model": "gpt-test",
        "duration_ms": 850,
        "prompt_tokens": 100,
        "completion_tokens": 25,
        "fallback_reason": "citation_check_failed",
    },
)
```

Counters:

- `llm_calls_total`
- `llm_calls_succeeded` / `llm_calls_failed`
- `llm_calls_fallback`

Observations:

- `llm_duration_ms`
- `llm_prompt_tokens`
- `llm_completion_tokens`
- `llm_total_tokens`

Event:

- `llm-result` with route, model, provider, status, latency, token counts,
  fallback reason, and error details.

The helper accepts `status` or `llm_status`; values such as `failed`,
`failure`, and `timeout` are normalized to `error`. If `total_tokens` is not
provided, it is derived from prompt and completion tokens.

## Stage summary

`summary_by_stage()` returns one object per stage:

```json
{
  "retrieval": {
    "event_count": 0,
    "span_count": 1,
    "error_span_count": 0,
    "duration_ms": {
      "count": 1,
      "total": 32.5,
      "min": 32.5,
      "max": 32.5,
      "avg": 32.5
    },
    "counters": {
      "queries_total": 1
    },
    "observations": {
      "retrieval_top_k": {
        "count": 3,
        "min": 4.0,
        "max": 8.0,
        "avg": 6.667,
        "distribution": {
          "4": 1,
          "8": 2
        }
      }
    }
  }
}
```

## Runtime integrations

- ChatFlow: wraps attachment indexing, course retrieval, web search, answer
  generation, and citation checking. The response keeps existing fields and adds
  a compact `telemetry` object for request diagnostics.
- Index jobs: expose durable job status through `GET /api/index-jobs/{job_id}`
  with progress, current file, timestamps, and per-file error details. Job
  snapshots are stored in `data/index_jobs.json`; interrupted queued/running
  jobs are restored as failed diagnostic records on restart.
- Future parsing and summary integrations can reuse the same recorder and result
  helpers without changing the payload shape.

The result helpers are deliberately separate from spans. A later integration can
use both: span wraps the operation duration and exception path, while the helper
records the normalized result payload after the operation returns.

The module should stay request-local or job-local. It is not a persistent
monitoring platform, and it deliberately avoids secrets such as API keys in
returned attributes.
