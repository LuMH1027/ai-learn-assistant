import unittest

from local_course_agent.agent_strategy import build_agent_trace


class AgentStrategyTest(unittest.TestCase):
    def test_trace_exposes_generic_agent_style_loop(self):
        trace = build_agent_trace(
            course_name="操作系统",
            question="页表有什么作用？",
            has_attachments=True,
            citation_count=2,
            memory_updated=True,
        )

        labels = [step["label"] for step in trace]
        self.assertEqual(labels, ["感知", "读取", "检索", "回答", "记忆"])
        self.assertIn("操作系统", trace[0]["detail"])
        self.assertEqual(trace[2]["status"], "ok")
        self.assertEqual(trace[-1]["status"], "ok")


if __name__ == "__main__":
    unittest.main()
