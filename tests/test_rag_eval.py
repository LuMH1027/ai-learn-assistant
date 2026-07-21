import json
import tempfile
import unittest
from pathlib import Path

from local_course_agent.rag import CourseKnowledgeBase
from local_course_agent.rag_eval import (
    demo_eval_cases,
    index_sample_materials,
    load_eval_cases,
    render_markdown_report,
    run_demo_baseline,
    run_rag_eval,
    sample_eval_cases,
)


class RagEvalTest(unittest.TestCase):
    def test_eval_reports_hit_rates_and_quality_counts(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CourseKnowledgeBase(Path(tmp))
            kb.index_text("os", "book", "教材.md", "页表保存虚拟页到物理页框的映射，用于地址转换。")
            kb.index_text("os", "slides", "课件.md", "TLB 缓存常用页表项，可以加速地址转换。")
            cases_path = Path(tmp) / "cases.json"
            cases_path.write_text(
                json.dumps(
                    {
                        "cases": [
                            {
                                "id": "page-table",
                                "course_id": "os",
                                "question": "页表如何完成地址转换？",
                                "expected_files": ["教材.md"],
                                "min_quality": "partial",
                            },
                            {
                                "id": "tlb",
                                "course_id": "os",
                                "question": "TLB 为什么能加速访问？",
                                "expected_files": ["课件.md"],
                                "min_quality": "partial",
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            report = run_rag_eval(kb, load_eval_cases(cases_path))

            self.assertEqual(report["summary"]["total_cases"], 2)
            self.assertEqual(report["summary"]["passed_cases"], 2)
            self.assertEqual(report["summary"]["citation_hit_rate"], 1.0)
            self.assertEqual(report["summary"]["first_citation_hit_rate"], 1.0)
            self.assertGreaterEqual(report["summary"]["quality_counts"]["partial"], 0)
            self.assertIn("partial", report["summary"]["quality_distribution"])
            self.assertGreaterEqual(report["summary"]["average_top_score"], 0)

    def test_eval_marks_missing_expected_reference_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CourseKnowledgeBase(Path(tmp))
            kb.index_text("os", "book", "教材.md", "页表用于地址转换。")
            cases = load_eval_cases(
                _write_cases(
                    tmp,
                    [
                        {
                            "id": "wrong-source",
                            "course_id": "os",
                            "question": "页表是什么？",
                            "expected_files": ["不存在.md"],
                        }
                    ],
                )
            )

            report = run_rag_eval(kb, cases)
            result = report["cases"][0]

            self.assertFalse(result["passed"])
            self.assertFalse(result["citation_hit"])
            self.assertEqual(result["missing_expected_files"], ["不存在.md"])
            self.assertEqual(report["summary"]["pass_rate"], 0.0)

    def test_markdown_report_contains_case_details(self):
        report = {
            "summary": {
                "total_cases": 1,
                "passed_cases": 1,
                "pass_rate": 1.0,
                "citation_hit_rate": 1.0,
                "first_citation_hit_rate": 1.0,
                "sufficient_rate": 1.0,
                "average_top_score": 42,
                "quality_counts": {"none": 0, "partial": 0, "sufficient": 1},
                "quality_distribution": {"none": 0.0, "partial": 0.0, "sufficient": 1.0},
            },
            "cases": [
                {
                    "id": "page-table",
                    "course_id": "os",
                    "question": "页表是什么？",
                    "expected_files": ["教材.md"],
                    "returned_files": ["教材.md"],
                    "retrieval_quality": "sufficient",
                    "top_score": 42,
                    "missing_expected_files": [],
                    "passed": True,
                }
            ],
        }

        markdown = render_markdown_report(report)

        self.assertIn("# RAG Eval Report", markdown)
        self.assertIn("PASS page-table", markdown)
        self.assertIn("Citation hit rate: 100.00%", markdown)
        self.assertIn("Quality distribution: none 0.00%, partial 0.00%, sufficient 100.00%", markdown)

    def test_sample_eval_cases_match_repository_sample_files(self):
        cases = sample_eval_cases("os-demo")

        self.assertEqual([case.id for case in cases], ["os-process-thread", "os-page-table", "os-file-system"])
        self.assertTrue(all(case.course_id == "os-demo" for case in cases))
        self.assertTrue(all(case.expected_files == ["README.md"] for case in cases))

    def test_demo_eval_cases_cover_sample_material_courses(self):
        cases = demo_eval_cases()

        self.assertEqual(len(cases), 6)
        self.assertIn("ds-stack-queue", {case.id for case in cases})
        self.assertIn("demo-operating-system", {case.course_id for case in cases})
        self.assertIn("demo-data-structures", {case.course_id for case in cases})

    def test_index_sample_materials_and_demo_baseline_report_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            sample_root = Path(tmp) / "sample_materials"
            (sample_root / "操作系统").mkdir(parents=True)
            (sample_root / "数据结构").mkdir(parents=True)
            (sample_root / "操作系统" / "README.md").write_text(
                "进程是资源分配单位。线程是 CPU 调度单位。页表记录虚拟页到物理页框映射。文件系统管理文件、权限和空间分配。",
                encoding="utf-8",
            )
            (sample_root / "操作系统" / "复习题.txt").write_text(
                "1. 简述进程和线程的区别。2. 页表在虚拟内存管理中起什么作用？",
                encoding="utf-8",
            )
            (sample_root / "数据结构" / "树.md").write_text(
                "二叉搜索树左子树小于根节点，右子树大于根节点。平衡二叉树通过旋转保持树高接近对数级。",
                encoding="utf-8",
            )
            (sample_root / "数据结构" / "栈和队列.md").write_text(
                "栈是后进先出，常用于函数调用和括号匹配。队列是先进先出，常用于任务调度和广度优先搜索。",
                encoding="utf-8",
            )

            kb = CourseKnowledgeBase(Path(tmp) / "indexes")
            manifest = index_sample_materials(kb, sample_root=sample_root)
            report = run_demo_baseline(Path(tmp) / "baseline-indexes", sample_root=sample_root)
            markdown = render_markdown_report(report)

            self.assertEqual(len(manifest["indexed_files"]), 4)
            self.assertEqual(manifest["missing_files"], [])
            self.assertEqual(report["baseline"]["indexed_files"], 4)
            self.assertEqual(report["summary"]["total_cases"], 6)
            self.assertIn("citation_hit_rate", report["summary"])
            self.assertIn("quality_distribution", report["summary"])
            self.assertIn("# RAG Eval Baseline Report", markdown)
            self.assertIn("## Baseline", markdown)
            self.assertIn("Indexed files: 4", markdown)
            self.assertIn("Citation hit rate:", markdown)
            self.assertIn("Quality distribution:", markdown)


def _write_cases(tmp: str, cases):
    path = Path(tmp) / "cases.json"
    path.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
    return path


if __name__ == "__main__":
    unittest.main()
