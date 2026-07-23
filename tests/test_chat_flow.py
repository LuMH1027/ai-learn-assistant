import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from local_course_agent.api.chat import ChatFlow
from local_course_agent.api.chat.generation import AgentStep, ChatAnswerGenerator, plan_agent_step, synthesize_answer_stream
from local_course_agent.api.chat.steps import (
    build_attachment_context,
    build_retrieval_context,
    build_source_context,
)
from local_course_agent.llm.client import LLMRequestError


class FakeStore:
    def __init__(self):
        self.messages = []

    def list_messages(self, course_id, conversation_id=None):
        return []

    def add_message(self, course_id, role, content, citations=None, trace=None, conversation_id=None):
        self.messages.append(
            {
                "course_id": course_id,
                "conversation_id": conversation_id,
                "role": role,
                "content": content,
                "citations": citations or [],
                "trace": trace or [],
            }
        )

    def update_memory_from_question(self, course_id, question, conversation_id=None):
        return "- 关注 1 次：TLB"

    def get_memory(self, course_id, conversation_id=None):
        return ""


class FakeKnowledgeBase:
    def __init__(self):
        self.calls = []

    def answer(self, course_id, query):
        self.calls.append((course_id, query))
        return {
            "answer": "基于当前课程资料，可以这样理解：TLB 能缓存页表项。",
            "citations": [
                {
                    "file_name": "内存管理.md",
                    "quote": "TLB 能缓存页表项，减少访存次数。",
                    "score": 97.5,
                }
            ],
            "retrieval_quality": "partial",
            "retrieval_trace": {
                "selected": [
                    {
                        "file_name": "内存管理.md",
                        "section_title": "地址转换",
                        "retrieval_method": "bm25_rrf_mmr",
                    }
                ]
            },
        }


class ChatFlowTelemetryTest(unittest.TestCase):
    def test_answer_generator_skips_synthesis_for_clarification(self):
        events = []
        synthesis_calls = []

        def synthesize(*_args, **_kwargs):
            synthesis_calls.append(True)
            return "不应调用", "used"

        generator = ChatAnswerGenerator(emit=events.append, synthesize=synthesize)

        answer, status = generator.generate(
            mode="homework",
            needs_clarification=True,
            search_question="1",
            combined_result={"answer": "本地回答", "citations": []},
            image_paths=[],
            ai_config={"api_key": "configured"},
        )

        self.assertEqual(status, "skipped")
        self.assertEqual(answer, "本地回答")
        self.assertEqual(events, [{"type": "delta", "delta": answer}])
        self.assertEqual(synthesis_calls, [])

    def test_step_contexts_structure_retrieval_and_sources(self):
        attachment = build_attachment_context("", "附件内容" * 1000, [Path("/tmp/screen.png")])
        retrieval = build_retrieval_context(attachment.question, [], attachment)
        result = {
            "answer": "本地回答",
            "citations": [
                {
                    "file_name": "内存管理.md",
                    "quote": "TLB 能缓存页表项。",
                }
            ],
            "retrieval_trace": {"candidates": []},
        }
        web_sources = [{"source_type": "web", "file_name": "Web", "quote": "web quote"}]

        sources = build_source_context(result, web_sources, needs_clarification=False)

        self.assertEqual(attachment.question, "请阅读并总结我拖入的文件。")
        self.assertIn("拖入聊天框的文件内容", retrieval.search_question)
        self.assertIn("拖入聊天框的截图：screen.png", retrieval.search_question)
        self.assertIn("附件内容", retrieval.search_question)
        self.assertLessEqual(retrieval.search_question.count("附件内容"), 1000)
        self.assertEqual(sources.local_sources[0]["reference_label"], "L1")
        self.assertEqual(sources.local_sources[0]["source_type"], "local")
        self.assertEqual(sources.web_sources[0]["reference_label"], "W1")
        self.assertEqual(
            [source["reference_label"] for source in sources.citations],
            ["L1", "W1"],
        )
        self.assertIn("网页搜索补充", sources.combined_result["answer"])

    def test_run_with_only_attachment_uses_default_question_and_keeps_payload_shape(self):
        store = FakeStore()
        context = SimpleNamespace(
            config={"ai": {}, "web_search": {}},
            find_course=lambda _course_id: {"name": "操作系统"},
            kb=FakeKnowledgeBase(),
            store=store,
        )
        flow = ChatFlow(
            context=context,
            data_dir=Path("/tmp"),
            emit=lambda _event: None,
            index_uploads=lambda _course_id, _uploads: ("TLB 附件内容", []),
            retrieve_web=lambda _question, _result, _config, allow_web=True: ([], "skipped"),
            plan_step=lambda *args, **kwargs: AgentStep(action="course_search", query="TLB 附件内容", reason="test", llm_status="used")
            if not kwargs.get("observations")
            else AgentStep(action="final", answer="已总结：请阅读并总结我拖入的文件。 [L1]", reason="done", llm_status="used"),
            synthesize=lambda question, _result, image_paths=None, ai_config=None, mode="answer", previous_messages=None: (
                f"已总结：{question.splitlines()[0]} [L1]",
                "used",
            ),
        )

        payload = flow.run("course-1", {"question": "", "mode": "answer"}, [{"filename": "notes.md"}])

        self.assertEqual(store.messages[0]["content"], "请阅读并总结我拖入的文件。")
        self.assertEqual(payload["mode"], "answer")
        self.assertEqual(payload["web_search_status"], "skipped")
        self.assertIn("telemetry", payload)
        self.assertEqual(payload["citations"][0]["reference_label"], "L1")

    def test_light_chat_uses_llm_responder_without_retrieval_or_web(self):
        store = FakeStore()
        kb = FakeKnowledgeBase()
        web_calls = []
        synthesize_calls = []
        context = SimpleNamespace(
            config={"ai": {}, "web_search": {}},
            find_course=lambda _course_id: {"name": "操作系统"},
            kb=kb,
            store=store,
        )
        planner = mock.Mock(return_value=AgentStep(
            action="final",
            answer="",
            reason="简单问候直接进入最终回答器",
            llm_status="used",
        ))
        flow = ChatFlow(
            context=context,
            data_dir=Path("/tmp"),
            emit=lambda _event: None,
            index_uploads=lambda _course_id, _uploads: ("", []),
            retrieve_web=lambda *args, **kwargs: web_calls.append((args, kwargs)) or ([], "used"),
            plan_step=planner,
            synthesize=lambda question, _result, image_paths=None, ai_config=None, mode="answer", previous_messages=None: (
                synthesize_calls.append(question) or "LLM 生成的问候回答",
                "used",
            ),
        )

        payload = flow.run("course-1", {"question": "你好", "mode": "answer"}, [])

        self.assertEqual(kb.calls, [])
        self.assertEqual(web_calls, [])
        planner.assert_called_once()
        self.assertEqual(synthesize_calls, ["你好"])
        self.assertEqual(payload["retrieval_trace"]["decision"], "react_pending")
        self.assertEqual(payload["web_search_status"], "skipped")
        self.assertEqual("LLM 生成的问候回答", payload["answer"])
        retrieval_step = next(step for step in store.messages[-1]["trace"] if step["label"] == "检索")
        self.assertEqual(retrieval_step["status"], "skip")

    def test_light_chat_with_configured_ai_uses_stream_responder(self):
        store = FakeStore()
        events = []
        context = SimpleNamespace(
            config={"ai": {"base_url": "http://llm", "api_key": "key", "model": "model"}, "web_search": {}},
            find_course=lambda _course_id: {"name": "操作系统"},
            kb=FakeKnowledgeBase(),
            store=store,
        )
        planner = mock.Mock(return_value=AgentStep(
            action="final",
            reason="用户问候属于闲聊，直接回答无需工具",
            llm_status="used",
        ))
        flow = ChatFlow(
            context=context,
            data_dir=Path("/tmp"),
            emit=events.append,
            stream_format="sse",
            index_uploads=lambda _course_id, _uploads: ("", []),
            retrieve_web=lambda *args, **kwargs: ([], "skipped"),
            plan_step=planner,
            synthesize_stream=mock.Mock(return_value=("LLM 流式问候回答", "used")),
        )

        payload = flow.run("course-1", {"question": "你好", "mode": "answer"}, [])

        self.assertEqual(payload["answer"], "LLM 流式问候回答")
        planner.assert_called_once()
        flow.answer_generator.synthesize_stream.assert_called_once()

    def test_identity_question_uses_llm_responder_instead_of_fixed_fallback(self):
        store = FakeStore()
        synthesize_calls = []
        events = []
        context = SimpleNamespace(
            config={"ai": {"base_url": "http://llm", "api_key": "key", "model": "model"}, "web_search": {}},
            find_course=lambda _course_id: {"name": "操作系统"},
            kb=FakeKnowledgeBase(),
            store=store,
        )
        planner = mock.Mock(return_value=AgentStep(
            action="final",
            reason="身份问题无需检索，但需要模型生成最终回答",
            llm_status="used",
        ))
        flow = ChatFlow(
            context=context,
            data_dir=Path("/tmp"),
            emit=events.append,
            index_uploads=lambda _course_id, _uploads: ("", []),
            retrieve_web=lambda *args, **kwargs: ([], "skipped"),
            plan_step=planner,
            synthesize=lambda question, _result, image_paths=None, ai_config=None, mode="answer", previous_messages=None: (
                synthesize_calls.append(question) or "我是由 LLM 生成的课程学习助手回答。",
                "used",
            ),
        )

        payload = flow.run("course-1", {"question": "你是谁", "mode": "answer"}, [])

        self.assertEqual(synthesize_calls, ["你是谁"])
        planner.assert_called_once()
        self.assertEqual(payload["answer"], "我是由 LLM 生成的课程学习助手回答。")
        self.assertIn(
            {"type": "status", "stage": "responder", "detail": "正在调用最终模型生成回答…"},
            events,
        )

    def test_course_search_with_evidence_skips_second_planner_call(self):
        store = FakeStore()
        kb = FakeKnowledgeBase()
        planner = mock.Mock(return_value=AgentStep(
            action="course_search",
            query="解释 TLB",
            reason="需要课程资料",
            llm_status="used",
        ))
        context = SimpleNamespace(
            config={"ai": {"base_url": "http://llm", "api_key": "key", "model": "model"}, "web_search": {}},
            find_course=lambda _course_id: {"name": "操作系统"},
            kb=kb,
            store=store,
        )
        flow = ChatFlow(
            context=context,
            data_dir=Path("/tmp"),
            emit=lambda _event: None,
            index_uploads=lambda _course_id, _uploads: ("", []),
            retrieve_web=lambda *args, **kwargs: ([], "skipped"),
            plan_step=planner,
            synthesize=lambda question, _result, image_paths=None, ai_config=None, mode="answer", previous_messages=None: (
                f"LLM 基于资料回答：{question}",
                "used",
            ),
        )

        payload = flow.run("course-1", {"question": "解释 TLB", "mode": "answer"}, [])

        self.assertEqual(planner.call_count, 1)
        self.assertEqual(kb.calls, [("course-1", "解释 TLB")])
        self.assertEqual(payload["answer"], "LLM 基于资料回答：解释 TLB")

    def test_planner_failure_does_not_treat_short_course_question_as_greeting(self):
        class BrokenClient:
            def enabled(self):
                return True

            def generate(self, *_args, **_kwargs):
                raise LLMRequestError("down")

        step = plan_agent_step(
            "讲一下知识点",
            course_name="操作系统",
            llm_client_factory=lambda _config: BrokenClient(),
        )

        self.assertEqual(step.action, "course_search")
        self.assertEqual(step.query, "讲一下知识点")

    def test_stream_responder_failure_emits_fallback_answer_when_course_result_exists(self):
        class BrokenClient:
            def enabled(self):
                return True

            def stream(self, *_args, **_kwargs):
                raise LLMRequestError("stream down")

            def generate(self, *_args, **_kwargs):
                raise LLMRequestError("generate down")

        events = []
        answer, status = synthesize_answer_stream(
            "讲一下知识点",
            {"answer": "课程资料里的本地回答", "citations": []},
            events.append,
            llm_client_factory=lambda _config: BrokenClient(),
        )

        self.assertEqual(answer, "课程资料里的本地回答")
        self.assertEqual(status, "fallback")
        self.assertEqual(events, ["课程资料里的本地回答"])

    def test_stream_responder_failure_without_local_answer_reports_model_unavailable(self):
        class BrokenClient:
            def enabled(self):
                return True

            def stream(self, *_args, **_kwargs):
                raise LLMRequestError("stream down")

            def generate(self, *_args, **_kwargs):
                raise LLMRequestError("generate down")

        events = []
        answer, status = synthesize_answer_stream(
            "你是谁",
            {"answer": "", "citations": []},
            events.append,
            llm_client_factory=lambda _config: BrokenClient(),
        )

        self.assertIn("当前大模型不可用", answer)
        self.assertEqual(status, "fallback")
        self.assertEqual(events, [answer])

    def test_run_returns_compact_telemetry_without_leaking_config_secrets(self):
        store = FakeStore()
        context = SimpleNamespace(
            config={
                "ai": {"api_key": "secret-token", "model": "course-model"},
                "web_search": {"enabled": True, "api_key": "web-secret-token"},
            },
            find_course=lambda _course_id: {"name": "操作系统"},
            kb=FakeKnowledgeBase(),
            store=store,
        )
        flow = ChatFlow(
            context=context,
            data_dir=Path("/tmp"),
            emit=lambda _event: None,
            index_uploads=lambda _course_id, _uploads: ("", []),
            retrieve_web=lambda _question, _result, _config, allow_web=True, force_search=False: (
                [
                    {
                        "source_type": "web",
                        "file_name": "Example",
                        "url": "https://example.edu/tlb",
                        "quote": "TLB is a cache for page table entries.",
                    }
                ],
                "used",
            ),
            plan_step=lambda *args, **kwargs: AgentStep(
                action="course_and_web_search",
                query="解释 TLB",
                reason="test",
                llm_status="used",
            )
            if not kwargs.get("observations")
            else AgentStep(
                action="final",
                answer="TLB 能缓存页表项，减少访存次数。[L1]",
                reason="done",
                llm_status="used",
            ),
            synthesize=lambda _question, _result, image_paths=None, ai_config=None, mode="answer", previous_messages=None: (
                "TLB 能缓存页表项，减少访存次数。[L1]",
                "used",
            ),
        )

        payload = flow.run("course-1", {"question": "解释 TLB", "mode": "answer"}, [])

        for key in (
            "answer",
            "citations",
            "memory",
            "mode",
            "trace",
            "retrieval_trace",
            "citation_check",
            "unsupported_claims",
            "llm_status",
            "web_search_status",
        ):
            self.assertIn(key, payload)
        self.assertIn("telemetry", payload)
        self.assertEqual(payload["llm_status"], "used")
        self.assertEqual(payload["web_search_status"], "used")

        telemetry = payload["telemetry"]
        self.assertEqual(
            {"indexing", "retrieval", "web", "llm", "citation_check"},
            set(telemetry["summary"]),
        )
        self.assertIn(
            "course-retrieval",
            {span["name"] for span in telemetry["spans"]},
        )
        self.assertIn(
            "web-result",
            {event["name"] for event in telemetry["events"]},
        )
        self.assertEqual(
            telemetry["summary"]["web"]["observations"]["web_source_count"]["avg"],
            1.0,
        )
        self.assertEqual(
            telemetry["summary"]["retrieval"]["counters"]["retrieval_queries_insufficient"],
            1.0,
        )

        encoded = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("secret-token", encoded)
        self.assertNotIn("web-secret-token", encoded)
        self.assertNotIn("api_key", encoded)

    def test_legacy_modes_return_normalized_guide_and_use_responder(self):
        store = FakeStore()
        context = SimpleNamespace(
            config={"ai": {}, "web_search": {}},
            find_course=lambda _course_id: {"name": "操作系统"},
            kb=FakeKnowledgeBase(),
            store=store,
        )
        seen = {}
        flow = ChatFlow(
            context=context,
            data_dir=Path("/tmp"),
            emit=lambda _event: None,
            index_uploads=lambda _course_id, _uploads: ("", []),
            retrieve_web=lambda *args, **kwargs: ([], "skipped"),
            plan_step=lambda *args, **kwargs: AgentStep(action="final", reason="done", llm_status="used"),
            synthesize=lambda _question, _result, image_paths=None, ai_config=None, mode="answer", previous_messages=None: (
                seen.setdefault("mode", mode) or "提示回答",
                "used",
            ),
        )

        payload = flow.run("course-1", {"question": "提示一下", "mode": "homework"}, [])

        self.assertEqual(payload["mode"], "guide")
        self.assertEqual(seen["mode"], "guide")


if __name__ == "__main__":
    unittest.main()
