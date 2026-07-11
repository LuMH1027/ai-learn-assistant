import unittest
from unittest import mock

from local_course_agent.llm import OpenAICompatibleClient, build_grounded_prompt


class LlmPromptTest(unittest.TestCase):
    def test_grounded_prompt_requires_citations_and_no_fabrication(self):
        prompt = build_grounded_prompt(
            question="页表有什么作用？",
            evidence=[
                {
                    "file_name": "README.md",
                    "page": None,
                    "chunk_index": 1,
                    "quote": "页表用于记录虚拟页到物理页框之间的映射关系。",
                }
            ],
            memory="- 最近关注：虚拟内存",
        )

        self.assertIn("只能依据资料片段回答", prompt)
        self.assertIn("页表有什么作用", prompt)
        self.assertIn("README.md", prompt)
        self.assertIn("如果资料片段不足", prompt)

    def test_openai_compatible_client_uses_chat_completions_endpoint(self):
        client = OpenAICompatibleClient(
            base_url="https://api.deepseek.com",
            api_key="test-key",
            model="deepseek-chat",
        )
        fake_response = mock.Mock()
        fake_response.__enter__ = mock.Mock(return_value=fake_response)
        fake_response.__exit__ = mock.Mock(return_value=None)
        fake_response.read.return_value = b'{"choices":[{"message":{"content":"answer"}}]}'

        with mock.patch("urllib.request.urlopen", return_value=fake_response) as urlopen:
            result = client.generate("hello")

        request = urlopen.call_args.args[0]
        self.assertEqual(result, "answer")
        self.assertEqual(request.full_url, "https://api.deepseek.com/chat/completions")
        self.assertEqual(request.headers["Authorization"], "Bearer test-key")


if __name__ == "__main__":
    unittest.main()
