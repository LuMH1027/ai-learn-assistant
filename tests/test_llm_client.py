import unittest
import tempfile
from pathlib import Path
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
            base_url="https://api.siliconflow.cn/v1",
            api_key="test-key",
            model="Pro/moonshotai/Kimi-K2.6",
        )
        fake_response = mock.Mock()
        fake_response.__enter__ = mock.Mock(return_value=fake_response)
        fake_response.__exit__ = mock.Mock(return_value=None)
        fake_response.read.return_value = b'{"choices":[{"message":{"content":"answer"}}]}'

        with mock.patch("urllib.request.urlopen", return_value=fake_response) as urlopen:
            result = client.generate("hello")

        request = urlopen.call_args.args[0]
        self.assertEqual(result, "answer")
        self.assertEqual(request.full_url, "https://api.siliconflow.cn/v1/chat/completions")
        self.assertEqual(request.headers["Authorization"], "Bearer test-key")

    def test_openai_compatible_client_sends_images_as_content_parts(self):
        client = OpenAICompatibleClient(
            base_url="https://api.siliconflow.cn/v1",
            api_key="test-key",
            model="Pro/moonshotai/Kimi-K2.6",
        )
        fake_response = mock.Mock()
        fake_response.__enter__ = mock.Mock(return_value=fake_response)
        fake_response.__exit__ = mock.Mock(return_value=None)
        fake_response.read.return_value = b'{"choices":[{"message":{"content":"image answer"}}]}'

        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "screen.png"
            image.write_bytes(b"fake-png")
            with mock.patch("urllib.request.urlopen", return_value=fake_response) as urlopen:
                result = client.generate_with_images("讲解截图", [image])

        request = urlopen.call_args.args[0]
        payload = request.data.decode("utf-8")
        self.assertEqual(result, "image answer")
        self.assertIn('"type": "image_url"', payload)
        self.assertIn("data:image/png;base64", payload)


if __name__ == "__main__":
    unittest.main()
