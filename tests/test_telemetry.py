import json
import unittest

from local_course_agent.ops.telemetry_core import TelemetryRecorder as CoreTelemetryRecorder
from local_course_agent.ops.telemetry_recorders import record_llm_result as record_llm_result_from_recorders
from local_course_agent.ops.telemetry import (
    TelemetryRecorder,
    record_index_result,
    record_llm_result,
    record_retrieval_result,
)


class FakeClock:
    def __init__(self):
        self.current = 100.0

    def __call__(self):
        return self.current

    def advance(self, seconds):
        self.current += seconds


class TelemetryRecorderTest(unittest.TestCase):
    def test_legacy_telemetry_module_reexports_split_modules(self):
        self.assertIs(TelemetryRecorder, CoreTelemetryRecorder)
        self.assertIs(record_llm_result, record_llm_result_from_recorders)

    def test_span_records_duration_and_stage_summary(self):
        clock = FakeClock()
        telemetry = TelemetryRecorder(clock=clock)

        with telemetry.span("build-index", stage="indexing", attributes={"course_id": "os"}) as span:
            self.assertEqual(span.status, "running")
            clock.advance(0.125)

        self.assertEqual(len(telemetry.spans), 1)
        self.assertEqual(telemetry.spans[0].status, "ok")
        self.assertEqual(telemetry.spans[0].duration_ms, 125.0)
        self.assertEqual(telemetry.spans[0].attributes["course_id"], "os")
        self.assertEqual(telemetry.summary_by_stage()["indexing"]["duration_ms"]["total"], 125.0)

    def test_span_marks_exceptions_and_reraises(self):
        clock = FakeClock()
        telemetry = TelemetryRecorder(clock=clock)

        with self.assertRaises(RuntimeError):
            with telemetry.span("llm-summary", stage="llm"):
                clock.advance(0.02)
                raise RuntimeError("timeout")

        span = telemetry.spans[0]
        self.assertEqual(span.status, "error")
        self.assertEqual(span.duration_ms, 20.0)
        self.assertEqual(span.attributes["error_type"], "RuntimeError")
        self.assertEqual(telemetry.summary_by_stage()["llm"]["error_span_count"], 1)

    def test_events_counters_and_observations_are_serializable(self):
        clock = FakeClock()
        telemetry = TelemetryRecorder(clock=clock)

        telemetry.event("parse-started", stage="parsing", attributes={"file": "a.pdf"})
        telemetry.increment("files_total", stage="parsing")
        telemetry.increment("files_failed", stage="parsing", amount=2)
        telemetry.observe("retrieval_top_k", 4, stage="retrieval")
        telemetry.observe("retrieval_top_k", 8, stage="retrieval")
        telemetry.observe("retrieval_top_k", 8, stage="retrieval")

        payload = telemetry.to_dict()
        encoded = telemetry.to_json()
        decoded = json.loads(encoded)

        self.assertEqual(payload["summary"]["parsing"]["event_count"], 1)
        self.assertEqual(payload["summary"]["parsing"]["counters"]["files_total"], 1.0)
        self.assertEqual(payload["summary"]["parsing"]["counters"]["files_failed"], 2.0)
        self.assertEqual(decoded["events"][0]["attributes"]["file"], "a.pdf")
        self.assertEqual(
            decoded["summary"]["retrieval"]["observations"]["retrieval_top_k"]["distribution"],
            {"4": 1, "8": 2},
        )

    def test_manual_span_finish_is_idempotent(self):
        clock = FakeClock()
        telemetry = TelemetryRecorder(clock=clock)
        context = telemetry.span("search", stage="retrieval")

        context.__enter__()
        clock.advance(0.01)
        first = context.finish("ok")
        clock.advance(0.5)
        second = context.finish("ok")

        self.assertIs(first, second)
        self.assertEqual(len(telemetry.spans), 1)
        self.assertEqual(telemetry.spans[0].duration_ms, 10.0)

    def test_invalid_inputs_are_rejected(self):
        telemetry = TelemetryRecorder()

        with self.assertRaises(ValueError):
            telemetry.event("")
        with self.assertRaises(ValueError):
            telemetry.increment("files_failed", amount=-1)
        with self.assertRaises(ValueError):
            telemetry.span("x").finish("unknown")

    def test_record_index_result_normalizes_counts_and_failure(self):
        clock = FakeClock()
        telemetry = TelemetryRecorder(clock=clock)

        event = record_index_result(
            telemetry,
            {
                "course_id": "os",
                "status": "failed",
                "total_files": 5,
                "indexed_files": 3,
                "skipped_files": 1,
                "failed_files": 1,
                "chunk_count": 42,
                "duration_ms": 1200,
                "error_message": "parse failed",
            },
        )

        summary = telemetry.summary_by_stage()["indexing"]
        self.assertEqual(event.name, "index-result")
        self.assertEqual(event.attributes["status"], "error")
        self.assertEqual(event.attributes["course_id"], "os")
        self.assertEqual(summary["counters"]["index_jobs_total"], 1.0)
        self.assertEqual(summary["counters"]["index_jobs_failed"], 1.0)
        self.assertEqual(summary["counters"]["index_files_failed"], 1.0)
        self.assertEqual(summary["counters"]["index_chunks_total"], 42.0)
        self.assertEqual(summary["observations"]["index_files_total"]["avg"], 5.0)
        self.assertEqual(summary["observations"]["index_duration_ms"]["avg"], 1200.0)

    def test_record_retrieval_result_derives_counts_from_payload_lists(self):
        telemetry = TelemetryRecorder()

        event = record_retrieval_result(
            telemetry,
            {
                "strategy": "hybrid",
                "retrieval_quality": "partial",
                "sufficient": False,
                "citations": [{"id": "L1"}, {"id": "L2"}],
                "results": [{"chunk_id": "a"}, {"chunk_id": "b"}, {"chunk_id": "c"}],
                "retrieval_trace": [
                    {"method": "bm25", "file_name": "a.md"},
                    {"method": "vector", "file_name": "a.md"},
                    {"method": "vector", "file_name": "b.md"},
                ],
                "duration_ms": 33.5,
            },
        )

        summary = telemetry.summary_by_stage()["retrieval"]
        self.assertEqual(event.attributes["strategy"], "hybrid")
        self.assertEqual(event.attributes["citation_count"], 2.0)
        self.assertEqual(event.attributes["candidate_count"], 3.0)
        self.assertEqual(event.attributes["reranked_count"], 3.0)
        self.assertEqual(event.attributes["methods"], ["bm25", "vector"])
        self.assertEqual(event.attributes["files"], ["a.md", "b.md"])
        self.assertEqual(summary["counters"]["retrieval_queries_total"], 1.0)
        self.assertEqual(summary["counters"]["retrieval_queries_insufficient"], 1.0)
        self.assertEqual(summary["observations"]["retrieval_candidate_count"]["avg"], 3.0)
        self.assertEqual(summary["observations"]["retrieval_duration_ms"]["avg"], 33.5)

    def test_record_retrieval_result_handles_minimal_success_payload(self):
        telemetry = TelemetryRecorder()

        event = record_retrieval_result(telemetry, {"top_k": 6})

        summary = telemetry.summary_by_stage()["retrieval"]
        self.assertEqual(event.attributes["top_k"], 6.0)
        self.assertEqual(summary["counters"]["retrieval_queries_total"], 1.0)
        self.assertEqual(summary["counters"]["retrieval_queries_with_evidence"], 1.0)
        self.assertEqual(summary["observations"]["retrieval_top_k"]["distribution"], {"6": 1})

    def test_record_llm_result_tracks_tokens_and_fallback(self):
        telemetry = TelemetryRecorder()

        event = record_llm_result(
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

        summary = telemetry.summary_by_stage()["llm"]
        self.assertEqual(event.attributes["status"], "ok")
        self.assertEqual(event.attributes["total_tokens"], 125.0)
        self.assertEqual(summary["counters"]["llm_calls_total"], 1.0)
        self.assertEqual(summary["counters"]["llm_calls_succeeded"], 1.0)
        self.assertEqual(summary["counters"]["llm_calls_fallback"], 1.0)
        self.assertEqual(summary["observations"]["llm_total_tokens"]["avg"], 125.0)

    def test_record_llm_result_tracks_error_payload(self):
        telemetry = TelemetryRecorder()

        event = record_llm_result(
            telemetry,
            {
                "llm_status": "timeout",
                "task": "summary",
                "model_name": "gpt-test",
                "latency_ms": "1500",
                "error_type": "TimeoutError",
            },
        )

        summary = telemetry.summary_by_stage()["llm"]
        self.assertEqual(event.attributes["status"], "error")
        self.assertEqual(event.attributes["route"], "summary")
        self.assertEqual(summary["counters"]["llm_calls_failed"], 1.0)
        self.assertEqual(summary["observations"]["llm_duration_ms"]["avg"], 1500.0)


if __name__ == "__main__":
    unittest.main()
