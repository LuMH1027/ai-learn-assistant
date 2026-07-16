import unittest
from unittest import mock

from local_course_agent.server import Handler, should_index_course_file


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


class ServerLlmRoutingTest(unittest.TestCase):
    def test_web_search_is_skipped_when_local_evidence_is_sufficient(self):
        handler = Handler.__new__(Handler)

        with mock.patch("local_course_agent.server.create_web_search_client") as factory:
            sources, status = handler.retrieve_web_sources(
                "解释页表",
                {"retrieval_quality": "sufficient", "citations": [{}]},
                {"enabled": True},
            )

        self.assertEqual((sources, status), ([], "skipped"))
        factory.assert_not_called()

    def test_web_search_runs_for_missing_local_evidence(self):
        source = {"source_type": "web", "url": "https://example.edu", "file_name": "Example"}
        client = FakeWebClient([source])
        handler = Handler.__new__(Handler)

        with mock.patch("local_course_agent.server.create_web_search_client", return_value=client):
            sources, status = handler.retrieve_web_sources(
                "解释量子纠缠",
                {"retrieval_quality": "none", "citations": []},
                {"enabled": True},
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

        with mock.patch("local_course_agent.server.create_llm_client", return_value=client):
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

        with mock.patch("local_course_agent.server.create_llm_client", return_value=client):
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

        with mock.patch("local_course_agent.server.create_llm_client", return_value=client):
            answer, status = handler.synthesize_answer(
                "解释页表",
                {"answer": "本地回退", "citations": []},
                ai_config={},
            )

        self.assertEqual(answer, "本地回退")
        self.assertEqual(status, "disabled")


if __name__ == "__main__":
    unittest.main()
