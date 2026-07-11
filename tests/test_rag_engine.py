import tempfile
import unittest
from pathlib import Path

from local_course_agent.rag import CourseKnowledgeBase


class CourseKnowledgeBaseTest(unittest.TestCase):
    def test_query_is_limited_to_current_course_and_returns_citations(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = Path(tmp)
            kb = CourseKnowledgeBase(storage)
            kb.index_text(
                course_id="os",
                file_id="os-file",
                file_name="process.md",
                text="进程是资源分配和调度的基本单位。页表用于虚拟内存地址映射。",
            )
            kb.index_text(
                course_id="math",
                file_id="math-file",
                file_name="calculus.md",
                text="导数描述函数变化率，积分描述累积量。",
            )

            result = kb.answer("os", "什么是页表？")

            self.assertIn("页表", result["answer"])
            self.assertEqual(result["citations"][0]["file_name"], "process.md")
            self.assertNotIn("calculus.md", result["answer"])

    def test_unknown_question_reports_no_reliable_basis(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CourseKnowledgeBase(Path(tmp))
            kb.index_text("os", "f1", "intro.md", "操作系统负责管理计算机资源。")

            result = kb.answer("os", "量子纠缠是什么？")

            self.assertIn("未在当前课程资料中找到可靠依据", result["answer"])
            self.assertEqual(result["citations"], [])

    def test_generate_summary_and_quiz_from_course_chunks(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CourseKnowledgeBase(Path(tmp))
            kb.index_text("ds", "stack", "栈.md", "栈是后进先出的线性表，常用于函数调用和括号匹配。")
            kb.index_text("ds", "queue", "队列.md", "队列是先进先出的线性表，常用于任务调度和广度优先搜索。")

            summary = kb.generate_summary("ds")
            quiz = kb.generate_quiz("ds", count=2)

            self.assertIn("课程复习摘要", summary["content"])
            self.assertGreaterEqual(len(summary["citations"]), 2)
            self.assertIn("自测题", quiz["content"])
            self.assertEqual(len(quiz["citations"]), 2)


if __name__ == "__main__":
    unittest.main()
