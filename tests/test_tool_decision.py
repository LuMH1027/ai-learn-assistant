import unittest

from local_course_agent.api.chat.generation import (
    ToolDecision,
    fallback_tool_decision,
    generate_tool_decision,
    parse_tool_decision,
)


class ToolDecisionTest(unittest.TestCase):
    def test_parse_direct_answer_skips_tools(self):
        parsed = parse_tool_decision(
            '{"direct_answer":"你好，我在。","use_course_materials":true,"use_web_search":true,"needs_clarification":false,"reason":"闲聊"}'
        )

        self.assertEqual(parsed["direct_answer"], "你好，我在。")
        self.assertFalse(parsed["use_course_materials"])
        self.assertFalse(parsed["use_web_search"])

    def test_parse_tool_request_keeps_model_selected_tools(self):
        parsed = parse_tool_decision(
            '{"direct_answer":"","use_course_materials":true,"use_web_search":false,"needs_clarification":false,"reason":"需要课程资料"}'
        )

        self.assertTrue(parsed["use_course_materials"])
        self.assertFalse(parsed["use_web_search"])

    def test_fallback_keeps_followups_on_course_materials(self):
        decision = fallback_tool_decision(
            "这个为什么更快？",
            has_attachments=False,
            has_previous_messages=True,
            llm_enabled=False,
        )

        self.assertEqual(decision, ToolDecision(use_course_materials=True, reason="模型不可用，追问场景本地降级为课程检索。"))

    def test_tool_decision_generation_uses_short_limits(self):
        calls = []

        class Client:
            def generate(self, prompt, max_tokens=None, timeout=None):
                calls.append((prompt, max_tokens, timeout))
                return '{"direct_answer":"好","reason":"短答"}'

        self.assertEqual(generate_tool_decision(Client(), "prompt"), '{"direct_answer":"好","reason":"短答"}')
        self.assertEqual(calls, [("prompt", 220, 12)])


if __name__ == "__main__":
    unittest.main()
