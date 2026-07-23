import io
import json
import tempfile
import unittest
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from local_course_agent.server import (
    CLARIFICATION_ANSWER,
    ClientDisconnected,
    Handler,
    course_index_stats,
    emit_stream_text,
    should_index_course_file,
)


class FakeClient:
    def __init__(self, generated, enabled=True):
        self.generated = generated
        self._enabled = enabled
        self.prompts = []

    def enabled(self):
        return self._enabled

    def generate(self, prompt):
        self.prompts.append(prompt)
        return self.generated

    def stream(self, prompt):
        self.prompts.append(prompt)
        if self.generated:
            yield from self.generated


class FakeWebClient:
    def __init__(self, sources, enabled=True):
        self.sources = sources
        self._enabled = enabled
        self.queries = []

    def enabled(self):
        return self._enabled

    def search(self, query):
        self.queries.append(query)
        return self.sources


class CapturingKb:
    def __init__(self):
        self.queries = []

    def answer(self, course_id, query):
        self.queries.append((course_id, query))
        return {
            "answer": "本地回答",
            "citations": [
                {
                    "file_name": "作业.md",
                    "quote": "TLB 能缓存页表项，减少访存次数。",
                    "score": 1.0,
                }
            ],
            "retrieval_quality": "sufficient",
            "retrieval_trace": {"candidates": []},
        }


class ServerLlmRoutingTest(unittest.TestCase):
    def test_numeric_only_question_skips_web_and_model_guessing(self):
        handler = Handler.__new__(Handler)
        handler.read_maybe_multipart = mock.Mock(return_value=({"question": "1", "mode": "answer"}, []))
        handler.index_chat_uploads = mock.Mock(return_value=("", []))
        handler.retrieve_web_sources = mock.Mock()
        handler.synthesize_answer = mock.Mock()
        handler.send_json = mock.Mock(side_effect=lambda payload: payload)
        store = mock.Mock()
        store.list_messages.return_value = []
        store.get_memory.return_value = ""
        context = SimpleNamespace(
            config={"ai": {}, "web_search": {}},
            find_course=lambda _course_id: {"name": "测试课程"},
            kb=SimpleNamespace(answer=lambda _course_id, _query: {
                "answer": "未找到依据",
                "citations": [],
                "retrieval_quality": "none",
            }),
            store=store,
        )

        with mock.patch("local_course_agent.server.CTX", context):
            payload = handler.chat("course-1")

        self.assertEqual(payload["answer"], CLARIFICATION_ANSWER)
        self.assertEqual(payload["citations"], [])
        self.assertEqual(payload["llm_status"], "skipped")
        self.assertEqual(payload["web_search_status"], "clarification")
        handler.retrieve_web_sources.assert_not_called()
        handler.synthesize_answer.assert_not_called()
        store.update_memory_from_question.assert_not_called()

    def test_chat_rewrites_numbered_follow_up_before_retrieval(self):
        handler = Handler.__new__(Handler)
        handler.read_maybe_multipart = mock.Mock(return_value=({"question": "第二问怎么做？", "mode": "answer"}, []))
        handler.index_chat_uploads = mock.Mock(return_value=("", []))
        handler.retrieve_web_sources = mock.Mock(return_value=([], "skipped"))
        handler.synthesize_answer = mock.Mock(return_value=("模型回答", "used"))
        handler.send_json = mock.Mock(side_effect=lambda payload: payload)
        kb = CapturingKb()
        store = mock.Mock()
        store.list_messages.return_value = [
            {
                "role": "user",
                "content": "1. 解释页表。2. TLB 为什么能加速地址转换？3. 缺页中断流程。",
            },
            {"role": "assistant", "content": "先判断每一问对应的知识点。"},
        ]
        store.update_memory_from_question.return_value = "- 关注 1 次：第二问"
        context = SimpleNamespace(
            config={"ai": {"api_key": "configured"}, "web_search": {}},
            find_course=lambda _course_id: {"name": "操作系统"},
            kb=kb,
            store=store,
        )

        with mock.patch("local_course_agent.server.CTX", context):
            payload = handler.chat("course-1")

        self.assertEqual(store.add_message.call_args_list[0].args[:3], ("course-1", "user", "第二问怎么做？"))
        self.assertEqual(kb.queries[0][0], "course-1")
        self.assertIn("TLB 为什么能加速地址转换", kb.queries[0][1])
        self.assertIn("当前追问", kb.queries[0][1])
        self.assertEqual(payload["retrieval_trace"]["contextual_query"]["used"], True)
        self.assertIn("第二", "".join(payload["retrieval_trace"]["contextual_query"]["signals"]))
        self.assertEqual(payload["trace"][2]["label"], "上下文")
        self.assertEqual(payload["trace"][2]["status"], "ok")

    def test_chat_rewrites_pronoun_follow_up_before_retrieval(self):
        handler = Handler.__new__(Handler)
        handler.read_maybe_multipart = mock.Mock(return_value=({"question": "这个为什么更快？", "mode": "answer"}, []))
        handler.index_chat_uploads = mock.Mock(return_value=("", []))
        handler.retrieve_web_sources = mock.Mock(return_value=([], "skipped"))
        handler.synthesize_answer = mock.Mock(return_value=("模型回答", "used"))
        handler.send_json = mock.Mock(side_effect=lambda payload: payload)
        kb = CapturingKb()
        store = mock.Mock()
        store.list_messages.return_value = [
            {"role": "user", "content": "TLB 在页表地址转换中起什么作用？"},
            {"role": "assistant", "content": "TLB 缓存常用页表项，减少访问页表的次数。"},
        ]
        store.update_memory_from_question.return_value = "- 关注 1 次：TLB"
        context = SimpleNamespace(
            config={"ai": {"api_key": "configured"}, "web_search": {}},
            find_course=lambda _course_id: {"name": "操作系统"},
            kb=kb,
            store=store,
        )

        with mock.patch("local_course_agent.server.CTX", context):
            payload = handler.chat("course-1")

        self.assertEqual(store.add_message.call_args_list[0].args[:3], ("course-1", "user", "这个为什么更快？"))
        self.assertIn("TLB 在页表地址转换中起什么作用", kb.queries[0][1])
        self.assertIn("这个为什么更快", kb.queries[0][1])
        self.assertTrue(payload["retrieval_trace"]["contextual_query"]["used"])
        self.assertIn("这个", payload["retrieval_trace"]["contextual_query"]["signals"])

    def test_broken_stream_connection_stops_generation(self):
        handler = Handler.__new__(Handler)
        handler.wfile = mock.Mock()
        handler.wfile.write.side_effect = BrokenPipeError

        with self.assertRaises(ClientDisconnected):
            handler.send_stream_event({"type": "delta", "delta": "停止"})

    def test_legacy_stream_splits_batched_text_into_display_units(self):
        events = []

        emit_stream_text("逐字 output!", events.append, paced=True, delay=0)

        self.assertEqual(
            [event["delta"] for event in events],
            ["逐", "字", " ", "output", "!"],
        )

    def test_stream_headers_disable_browser_mime_buffering(self):
        handler = Handler.__new__(Handler)
        handler.send_response = mock.Mock()
        handler.send_header = mock.Mock()
        handler.end_headers = mock.Mock()

        handler.begin_stream()

        handler.send_header.assert_any_call("Content-Type", "text/event-stream; charset=utf-8")
        handler.send_header.assert_any_call("X-Content-Type-Options", "nosniff")
        handler.send_header.assert_any_call("Transfer-Encoding", "chunked")
        self.assertEqual(Handler.protocol_version, "HTTP/1.1")

    def test_stream_events_use_http_chunk_framing(self):
        handler = Handler.__new__(Handler)
        handler.wfile = io.BytesIO()
        event = {"type": "status", "detail": "正在检索"}
        raw = ("data: " + json.dumps(event, ensure_ascii=False) + "\n\n").encode("utf-8")

        handler.send_stream_event(event)
        handler.end_stream()

        expected = f"{len(raw):X}\r\n".encode("ascii") + raw + b"\r\n0\r\n\r\n"
        self.assertEqual(handler.wfile.getvalue(), expected)

    def test_stream_keeps_ndjson_compatibility_for_open_legacy_tabs(self):
        handler = Handler.__new__(Handler)
        handler.send_response = mock.Mock()
        handler.send_header = mock.Mock()
        handler.end_headers = mock.Mock()
        handler.wfile = io.BytesIO()

        handler.begin_stream("ndjson")
        handler.send_stream_event({"type": "delta", "delta": "旧"}, "ndjson")

        handler.send_header.assert_any_call(
            "Content-Type", "application/x-ndjson; charset=utf-8"
        )
        framed = handler.wfile.getvalue()
        self.assertIn('{"type": "delta", "delta": "旧"}\n'.encode("utf-8"), framed)

    def test_config_status_endpoint_returns_sanitized_health_payload(self):
        handler = Handler.__new__(Handler)
        handler.path = "/api/config/status"
        handler.send_json = mock.Mock(side_effect=lambda payload: payload)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "materials"
            root.mkdir()
            context = SimpleNamespace(
                config={
                    "root_folder": str(root),
                    "ai": {
                        "base_url": "https://llm.example/v1",
                        "api_key": "secret-token",
                        "model": "course-model",
                    },
                },
                courses=lambda: [{"id": "course-1"}],
            )
            with (
                mock.patch("local_course_agent.server.CTX", context),
                mock.patch("local_course_agent.server.DATA_DIR", Path(tmp) / "data"),
            ):
                payload = handler.do_GET()

        self.assertEqual(payload["root_folder"], str(root))
        self.assertIn("capabilities", payload)
        self.assertNotIn("secret-token", json.dumps(payload, ensure_ascii=False))

    def test_streaming_synthesis_emits_model_deltas(self):
        client = FakeClient(["课程", "回答"])
        handler = Handler.__new__(Handler)
        deltas = []

        with mock.patch("local_course_agent.api.chat.create_llm_client", return_value=client):
            answer, status = handler.synthesize_answer_stream(
                "解释页表",
                {"answer": "本地回退", "citations": []},
                emit_delta=deltas.append,
                ai_config={"api_key": "configured"},
            )

        self.assertEqual(answer, "课程回答")
        self.assertEqual(status, "used")
        self.assertEqual(deltas, ["课程", "回答"])

    def test_web_search_is_skipped_when_local_evidence_is_sufficient(self):
        handler = Handler.__new__(Handler)

        with mock.patch("local_course_agent.api.chat.create_web_search_client") as factory:
            sources, status = handler.retrieve_web_sources(
                "解释页表",
                {"retrieval_quality": "sufficient", "citations": [{}]},
                {"enabled": True},
            )

        self.assertEqual((sources, status), ([], "skipped"))
        factory.assert_not_called()

    def test_web_search_waits_for_llm_tool_decision_when_local_evidence_is_missing(self):
        source = {"source_type": "web", "url": "https://example.edu", "file_name": "Example"}
        client = FakeWebClient([source])
        handler = Handler.__new__(Handler)

        with mock.patch("local_course_agent.api.chat.create_web_search_client", return_value=client):
            sources, status = handler.retrieve_web_sources(
                "解释量子纠缠",
                {"retrieval_quality": "none", "citations": []},
                {"enabled": True},
            )

        self.assertEqual((sources, status), ([], "skipped"))
        self.assertEqual(client.queries, [])

        with mock.patch("local_course_agent.api.chat.create_web_search_client", return_value=client):
            sources, status = handler.retrieve_web_sources(
                "解释量子纠缠",
                {"retrieval_quality": "none", "citations": []},
                {"enabled": True},
                force_search=True,
            )

        self.assertEqual(status, "used")
        self.assertEqual(sources, [source])
        self.assertEqual(client.queries, ["解释量子纠缠"])
    def test_generated_study_artifacts_are_not_reindexed_as_course_evidence(self):
        self.assertFalse(should_index_course_file("/courses/os", "/courses/os/AI生成/课程摘要.md"))
        self.assertTrue(should_index_course_file("/courses/os", "/courses/os/课件/第一章.md"))

    def test_configured_llm_is_called_even_without_retrieval_citations(self):
        client = FakeClient("我是课程学习助手。")
        handler = Handler.__new__(Handler)

        with mock.patch("local_course_agent.api.chat.create_llm_client", return_value=client):
            answer, status = handler.synthesize_answer(
                "你是谁",
                {"answer": "本地回退", "citations": []},
                ai_config={"api_key": "configured"},
            )

        self.assertEqual(answer, "我是课程学习助手。")
        self.assertEqual(status, "used")
        self.assertEqual(len(client.prompts), 1)
        self.assertIn("你是谁", client.prompts[0])

    def test_failed_configured_llm_reports_fallback_status(self):
        client = FakeClient(None)
        handler = Handler.__new__(Handler)

        with mock.patch("local_course_agent.api.chat.create_llm_client", return_value=client):
            answer, status = handler.synthesize_answer(
                "解释页表",
                {"answer": "本地回退", "citations": []},
                ai_config={"api_key": "configured"},
            )

        self.assertEqual(answer, "本地回退")
        self.assertEqual(status, "fallback")

    def test_disabled_llm_reports_disabled_status(self):
        client = FakeClient(None, enabled=False)
        handler = Handler.__new__(Handler)

        with mock.patch("local_course_agent.api.chat.create_llm_client", return_value=client):
            answer, status = handler.synthesize_answer(
                "解释页表",
                {"answer": "本地回退", "citations": []},
                ai_config={},
            )

        self.assertEqual(answer, "本地回退")
        self.assertEqual(status, "disabled")

    def test_dashboard_route_aggregates_store_and_index_stats(self):
        course = {
            "id": "course-1",
            "name": "操作系统",
            "path": "/courses/os",
            "children": [
                {
                    "type": "file",
                    "name": "内存管理.md",
                    "path": "/courses/os/内存管理.md",
                    "size": 100,
                }
            ],
        }
        store = SimpleNamespace(
            list_messages=lambda _course_id: [
                {"role": "user", "content": "解释页表", "created_at": "2026-07-21 10:00:00"}
            ],
            list_notes=lambda _course_id: [
                {"title": "TLB", "content": "命中后不查页表", "created_at": "2026-07-21 11:00:00"}
            ],
            list_study_plan=lambda _course_id: [
                {"id": 1, "title": "读课件", "kind": "read", "status": "done", "estimated_minutes": 30},
                {"id": 2, "title": "做练习", "kind": "practice", "status": "doing", "estimated_minutes": 45},
            ],
            get_mastery_state=lambda _course_id: {
                "knowledge_points": [{"id": "kp-tlb", "title": "TLB"}],
                "mastery": {"kp-tlb": {"score": 70, "level": "familiar"}},
                "mistakes": [],
            },
        )
        with tempfile.TemporaryDirectory() as tmp:
            index_path = Path(tmp) / "course-1.json"
            index_path.write_text(
                json.dumps(
                    {
                        "schema_version": 2,
                        "tokenizer_version": "zh_ngrams_v2",
                        "chunks": [
                            {"file_id": "f1", "file_name": "内存管理.md", "text": "页表"},
                            {"file_id": "f1", "file_name": "内存管理.md", "text": "TLB"},
                            {"file_id": "f2", "file_name": "练习.txt", "text": "地址转换"},
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            context = SimpleNamespace(
                find_course=lambda course_id: course if course_id == "course-1" else None,
                store=store,
                kb=SimpleNamespace(storage_dir=Path(tmp)),
            )
            handler = Handler.__new__(Handler)
            handler.path = "/api/courses/course-1/dashboard"
            handler.send_json = mock.Mock(side_effect=lambda payload, *args: payload)

            with mock.patch("local_course_agent.server.CTX", context):
                payload = handler.do_GET()

        dashboard = payload["dashboard"]
        self.assertEqual(dashboard["course"]["name"], "操作系统")
        self.assertEqual(dashboard["learning_progress"]["done"], 0)
        self.assertEqual(dashboard["learning_progress"]["doing"], 0)
        self.assertEqual(dashboard["materials"]["indexed_files"], 2)
        self.assertEqual(dashboard["materials"]["indexed_chunks"], 3)
        self.assertEqual(dashboard["materials"]["schema_version"], 2)
        self.assertEqual(dashboard["materials"]["tokenizer_version"], "zh_ngrams_v2")
        self.assertEqual(dashboard["mastery"]["tracked_count"], 1)
        self.assertEqual(dashboard["mastery"]["average_score"], 70)

    def test_mastery_routes_read_and_update_course_state(self):
        handler = Handler.__new__(Handler)
        handler.send_json = mock.Mock(side_effect=lambda payload, *args: payload)
        with tempfile.TemporaryDirectory() as tmp:
            from local_course_agent.store import AppStore

            store = AppStore(Path(tmp))
            context = SimpleNamespace(
                find_course=lambda course_id: {"id": "course-1", "name": "操作系统"} if course_id == "course-1" else None,
                store=store,
            )
            with mock.patch("local_course_agent.server.CTX", context):
                handler.path = "/api/courses/course-1/mastery"
                before = handler.do_GET()
                handler.read_body = mock.Mock(
                    return_value={
                        "knowledge_point": {"id": "kp-page-table", "title": "页表地址转换"},
                        "answer_result": {
                            "point_id": "kp-page-table",
                            "correct": "false",
                            "question": "解释页表地址转换。",
                            "user_answer": "直接查物理地址。",
                            "expected_answer": "页号查页表得到页框号，再拼接偏移。",
                        },
                    }
                )
                after = handler.do_POST()

        self.assertEqual(before["mastery"]["knowledge_points"], [])
        self.assertEqual(after["mastery"]["knowledge_points"][0]["id"], "kp-page-table")
        self.assertEqual(after["mastery"]["mastery"]["kp-page-table"]["wrong_count"], 1)
        self.assertEqual(after["mastery"]["mistakes"][0]["status"], "open")

    def test_dashboard_route_reports_missing_course(self):
        handler = Handler.__new__(Handler)
        handler.path = "/api/courses/missing/dashboard"
        handler.send_error_json = mock.Mock(side_effect=lambda message, status: {"error": message, "status": status})
        context = SimpleNamespace(find_course=lambda _course_id: None)

        with mock.patch("local_course_agent.server.CTX", context):
            payload = handler.do_GET()

        self.assertEqual(payload, {"error": "课程不存在", "status": HTTPStatus.NOT_FOUND})

    def test_course_index_stats_supports_legacy_list_indexes(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "course-1.json").write_text(
                json.dumps(
                    [
                        {"file_id": "f1", "file_name": "a.md"},
                        {"file_id": "f2", "file_name": "b.md"},
                        {"file_id": "f2", "file_name": "b.md"},
                    ],
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            stats = course_index_stats(SimpleNamespace(storage_dir=Path(tmp)), "course-1")

        self.assertEqual(stats["indexed_files"], 2)
        self.assertEqual(stats["total_chunks"], 3)
        self.assertIsNone(stats["schema_version"])


if __name__ == "__main__":
    unittest.main()
