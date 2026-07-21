import time
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from local_course_agent.course_service import (
    CourseIndexJobs,
    build_course_index,
    build_default_study_plan,
    generate_course_summary,
    study_plan_stats,
)
from local_course_agent.rag import CourseKnowledgeBase


class FakeSummaryClient:
    def __init__(self, generated=None, enabled=True):
        self.generated = generated
        self._enabled = enabled
        self.prompts = []

    def enabled(self):
        return self._enabled

    def generate(self, prompt):
        self.prompts.append(prompt)
        return self.generated


class CourseServiceTest(unittest.TestCase):
    def test_index_job_reports_successful_result(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "OS"
            source.mkdir()
            material = source / "notes.md"
            material.write_text("页表用于虚拟地址到物理地址转换。", encoding="utf-8")
            kb = CourseKnowledgeBase(Path(tmp) / "indexes")
            jobs = CourseIndexJobs(kb)

            started = jobs.start(
                "course-1",
                {
                    "path": str(source),
                    "children": [
                        {
                            "id": "notes",
                            "name": "notes.md",
                            "path": str(material),
                            "type": "file",
                        }
                    ],
                },
            )

            for _ in range(50):
                current = jobs.get(started["id"])
                if current and current["status"] == "succeeded":
                    break
                time.sleep(0.01)

            self.assertEqual(current["status"], "succeeded")
            self.assertEqual(current["result"]["indexed_files"], 1)
            self.assertGreaterEqual(current["result"]["total_chunks"], 1)

    def test_build_course_index_reports_parser_quality_for_low_quality_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "OS"
            source.mkdir()
            good = source / "notes.md"
            scanned = source / "scan.pdf"
            good_text = "页表用于虚拟地址到物理地址转换。TLB 可以缓存页表项，从而减少访问内存中的页表次数。"
            good.write_text(good_text, encoding="utf-8")
            scanned.write_bytes(b"%PDF placeholder")
            kb = CourseKnowledgeBase(Path(tmp) / "indexes")

            def fake_extract_text(path, mineru_config=None):
                if Path(path).name == "scan.pdf":
                    return [{"page": 1, "text": "需要 OCR 才能识别扫描件内容"}]
                return [{"page": 1, "text": good_text}]

            with mock.patch("local_course_agent.course_service.extract_text", side_effect=fake_extract_text):
                result = build_course_index(
                    kb,
                    {
                        "path": str(source),
                        "children": [
                            {
                                "id": "notes",
                                "name": "notes.md",
                                "path": str(good),
                                "type": "file",
                            },
                            {
                                "id": "scan",
                                "name": "scan.pdf",
                                "path": str(scanned),
                                "type": "file",
                            },
                        ],
                    },
                    "course-1",
                )

            self.assertEqual(result["indexed_files"], 2)
            self.assertGreaterEqual(result["total_chunks"], 1)
            self.assertEqual(result["parser_quality"]["counts"]["ok"], 1)
            self.assertEqual(result["parser_quality"]["counts"]["warning"], 1)
            self.assertEqual(result["parser_quality"]["counts"]["failed"], 0)

            files = {item["file_id"]: item for item in result["parser_quality"]["files"]}
            self.assertEqual(files["scan"]["file_name"], "scan.pdf")
            self.assertEqual(files["scan"]["status"], "warning")
            self.assertLess(files["scan"]["score"], 1.0)
            self.assertIn("ocr_placeholder", {warning["code"] for warning in files["scan"]["warnings"]})

    def test_default_study_plan_uses_real_course_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "OS"
            source.mkdir()
            lecture = source / "课件-进程.md"
            exercise = source / "练习题.txt"
            image = source / "diagram.png"
            lecture.write_text("进程管理", encoding="utf-8")
            exercise.write_text("调度练习", encoding="utf-8")
            image.write_bytes(b"image")

            plan = build_default_study_plan(
                {
                    "name": "操作系统",
                    "path": str(source),
                    "children": [
                        {
                            "id": "lecture",
                            "name": lecture.name,
                            "path": str(lecture),
                            "type": "file",
                        },
                        {
                            "id": "exercise",
                            "name": exercise.name,
                            "path": str(exercise),
                            "type": "file",
                        },
                        {
                            "id": "image",
                            "name": image.name,
                            "path": str(image),
                            "type": "file",
                        },
                    ],
                }
            )

            titles = [item["title"] for item in plan]

            self.assertIn("阅读并提炼 课件-进程.md", titles)
            self.assertIn("完成并订正 练习题.txt", titles)
            self.assertFalse(any("diagram.png" in title for title in titles))
            self.assertEqual(plan[-1]["kind"], "review")

    def test_study_plan_stats_report_progress_and_remaining_minutes(self):
        stats = study_plan_stats(
            [
                {"id": 1, "status": "done", "estimated_minutes": 30},
                {"id": 2, "status": "doing", "estimated_minutes": 20},
                {"id": 3, "status": "todo", "estimated_minutes": 10},
            ]
        )

        self.assertEqual(stats["completed"], 1)
        self.assertEqual(stats["doing"], 1)
        self.assertEqual(stats["remaining_minutes"], 30)
        self.assertEqual(stats["progress_percent"], 33)
        self.assertEqual(stats["next_item_id"], 2)

    def test_course_summary_uses_configured_llm(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CourseKnowledgeBase(Path(tmp))
            kb.index_text("ds", "stack", "栈.md", "栈是后进先出的线性表，常用于函数调用。")
            client = FakeSummaryClient("LLM 课程复习摘要\n\n## 总体脉络\n- 栈用于约束访问顺序。[S1]")

            with mock.patch("local_course_agent.course_service.create_llm_client", return_value=client):
                summary = generate_course_summary(kb, "ds", "数据结构", ai_config={"api_key": "configured"})

            self.assertEqual(summary["llm_status"], "used")
            self.assertIn("LLM 课程复习摘要", summary["content"])
            self.assertIn("数据结构", client.prompts[0])
            self.assertIn("栈.md", client.prompts[0])
            self.assertEqual(summary["citations"][0]["file_name"], "栈.md")

    def test_course_summary_falls_back_when_llm_is_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CourseKnowledgeBase(Path(tmp))
            kb.index_text("ds", "queue", "队列.md", "队列是先进先出的线性表，常用于任务调度。")
            client = FakeSummaryClient(None, enabled=False)

            with mock.patch("local_course_agent.course_service.create_llm_client", return_value=client):
                summary = generate_course_summary(kb, "ds", "数据结构", ai_config={})

            self.assertEqual(summary["llm_status"], "disabled")
            self.assertIn("课程复习摘要", summary["content"])
            self.assertIn("## 核心知识点", summary["content"])


if __name__ == "__main__":
    unittest.main()
