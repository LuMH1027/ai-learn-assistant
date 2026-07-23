import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from local_course_agent.api.chat import ChatFlow
from local_course_agent.api.chat.generation import AgentStep, ChatAnswerGenerator
from local_course_agent.api.chat.steps import (
    build_attachment_context,
    build_retrieval_context,
    build_source_context,
)


class FakeStore:
    def __init__(self):
        self.messages = []

    def list_messages(self, course_id):
        return []

    def add_message(self, course_id, role, content, citations=None, trace=None):
        self.messages.append(
            {
                "course_id": course_id,
                "role": role,
                "content": content,
                "citations": citations or [],
                "trace": trace or [],
            }
        )

    def update_memory_from_question(self, course_id, question):
        return "- 关注 1 次：TLB"

    def get_memory(self, course_id):
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
        self.assertTrue(answer.startswith("作业提示模式"))
        self.assertIn("你的问题信息不足", answer)
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
            synthesize=lambda question, _result, image_paths=None, ai_config=None: (
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

    def test_light_chat_uses_direct_model_without_retrieval_or_web(self):
        store = FakeStore()
        kb = FakeKnowledgeBase()
        web_calls = []
        context = SimpleNamespace(
            config={"ai": {}, "web_search": {}},
            find_course=lambda _course_id: {"name": "操作系统"},
            kb=kb,
            store=store,
        )
        flow = ChatFlow(
            context=context,
            data_dir=Path("/tmp"),
            emit=lambda _event: None,
            index_uploads=lambda _course_id, _uploads: ("", []),
            retrieve_web=lambda *args, **kwargs: web_calls.append((args, kwargs)) or ([], "used"),
            plan_step=lambda *args, **kwargs: AgentStep(
                action="final",
                answer="我在。",
                reason="test",
                llm_status="disabled",
            ),
        )

        payload = flow.run("course-1", {"question": "你好", "mode": "answer"}, [])

        self.assertEqual(kb.calls, [])
        self.assertEqual(web_calls, [])
        self.assertEqual(payload["retrieval_trace"]["decision"], "react_pending")
        self.assertEqual(payload["web_search_status"], "skipped")
        self.assertEqual("我在。", payload["answer"])
        retrieval_step = next(step for step in store.messages[-1]["trace"] if step["label"] == "检索")
        self.assertEqual(retrieval_step["status"], "skip")

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
            synthesize=lambda _question, _result, image_paths=None, ai_config=None: (
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


if __name__ == "__main__":
    unittest.main()
