import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from local_course_agent.api.chat import ChatFlow


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
    def answer(self, course_id, query):
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
            retrieve_web=lambda _question, _result, _config, allow_web=True: (
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
