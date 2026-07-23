import unittest

from local_course_agent.api.chat.generation import (
    AgentStep,
    fallback_agent_step,
    generate_agent_step,
    parse_agent_step,
)


class AgentStepTest(unittest.TestCase):
    def test_parse_final_answer_skips_tools(self):
        parsed = parse_agent_step(
            '{"action":"final","answer":"你好，我在。","query":"","reason":"闲聊"}'
        )

        self.assertEqual(parsed["action"], "final")
        self.assertEqual(parsed["answer"], "你好，我在。")

    def test_parse_combined_tool_request(self):
        parsed = parse_agent_step(
            '{"action":"course_and_web_search","answer":"","query":"比较课程内容和竞品","reason":"需要两类资料"}'
        )

        self.assertEqual(parsed["action"], "course_and_web_search")
        self.assertEqual(parsed["query"], "比较课程内容和竞品")

    def test_fallback_keeps_followups_on_course_materials(self):
        step = fallback_agent_step(
            "这个为什么更快？",
            has_attachments=False,
            has_previous_messages=True,
            has_observations=False,
            llm_enabled=False,
        )

        self.assertEqual(step, AgentStep(action="course_search", query="这个为什么更快？", reason="模型不可用，追问场景本地降级为课程检索。"))

    def test_agent_step_generation_uses_bounded_limits(self):
        calls = []

        class Client:
            def generate(self, prompt, max_tokens=None, timeout=None):
                calls.append((prompt, max_tokens, timeout))
                return '{"action":"final","answer":"好","reason":"短答"}'

        self.assertEqual(generate_agent_step(Client(), "prompt"), '{"action":"final","answer":"好","reason":"短答"}')
        self.assertEqual(calls, [("prompt", 900, 45)])


if __name__ == "__main__":
    unittest.main()
