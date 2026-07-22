import json
import tempfile
import unittest
from pathlib import Path

from local_course_agent.evaluation.rag_quality import evaluate_chatflow_payload, evaluate_summary_payload
from local_course_agent.retrieval.rag import CourseKnowledgeBase
from local_course_agent.retrieval.rag_eval import (
    demo_eval_cases,
    index_sample_materials,
    load_eval_cases,
    render_markdown_report,
    run_chatflow_structure_eval,
    run_demo_baseline,
    run_rag_eval,
    run_summary_pipeline_eval,
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

    def test_eval_can_require_final_answer_terms_and_forbid_hallucinated_terms(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CourseKnowledgeBase(Path(tmp))
            kb.index_text("os", "book", "教材.md", "页表保存虚拟页到物理页框的映射，用于地址转换。")
            cases = load_eval_cases(
                _write_cases(
                    tmp,
                    [
                        {
                            "id": "answer-quality",
                            "course_id": "os",
                            "question": "页表如何完成地址转换？",
                            "expected_files": ["教材.md"],
                            "expected_terms": ["虚拟页", "物理页框", "地址转换"],
                            "min_answer_term_rate": 0.67,
                            "forbidden_terms": ["量子纠缠"],
                        }
                    ],
                )
            )

            report = run_rag_eval(kb, cases)
            result = report["cases"][0]

            self.assertTrue(result["passed"])
            self.assertGreaterEqual(result["answer_term_rate"], 0.67)
            self.assertEqual(result["forbidden_term_hits"], [])
            self.assertEqual(report["summary"]["answer_term_pass_rate"], 1.0)
            self.assertEqual(report["summary"]["forbidden_term_pass_rate"], 1.0)

    def test_eval_can_fail_when_final_answer_has_unsupported_claims(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CourseKnowledgeBase(Path(tmp))
            kb.index_text("os", "book", "教材.md", "页表保存虚拟页到物理页框的映射，用于地址转换。")
            cases = load_eval_cases(
                _write_cases(
                    tmp,
                    [
                        {
                            "id": "strict-citation-support",
                            "course_id": "os",
                            "question": "页表如何完成地址转换？",
                            "expected_files": ["教材.md"],
                            "max_unsupported_claims": 0,
                        }
                    ],
                )
            )

            report = run_rag_eval(kb, cases)
            result = report["cases"][0]

            self.assertFalse(result["passed"])
            self.assertFalse(result["citation_support_ok"])
            self.assertGreater(result["unsupported_claim_count"], 0)
            self.assertEqual(report["summary"]["citation_support_pass_rate"], 0.0)

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
                "average_answer_term_rate": 1.0,
                "answer_term_pass_rate": 1.0,
                "citation_support_pass_rate": 1.0,
                "forbidden_term_pass_rate": 1.0,
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
            self.assertIn("chatflow_eval", report)
            self.assertIn("summary_eval", report)
            self.assertEqual(report["chatflow_eval"]["summary"]["passed_cases"], 3)
            self.assertEqual(report["summary_eval"]["summary"]["passed_cases"], 4)
            self.assertTrue(report["summary"]["quality_gate_passed"])
            self.assertIn("# RAG Eval Baseline Report", markdown)
            self.assertIn("## Baseline", markdown)
            self.assertIn("## ChatFlow Structure Eval", markdown)
            self.assertIn("## Summary Pipeline Eval", markdown)
            self.assertIn("Indexed files: 4", markdown)
            self.assertIn("Citation hit rate:", markdown)
            self.assertIn("Quality distribution:", markdown)

    def test_chatflow_structure_eval_runs_real_orchestration_and_follow_up_trace(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = _indexed_demo_kb(tmp)

            report = run_chatflow_structure_eval(kb)

            self.assertEqual(report["summary"]["total_cases"], 3)
            self.assertEqual(report["summary"]["passed_cases"], 3)
            follow_up = next(item for item in report["cases"] if item["id"] == "chatflow-context-follow-up")
            self.assertTrue(follow_up["metrics"]["contextual_query_used"])
            self.assertIn(follow_up["metrics"]["llm_status"], {"disabled", "fallback", "used"})
            self.assertIn(follow_up["metrics"]["web_search_status"], {"skipped", "disabled", "used", "empty"})

    def test_summary_pipeline_eval_checks_service_fallback_and_map_reduce_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = _indexed_demo_kb(tmp)

            report = run_summary_pipeline_eval(kb)

            self.assertEqual(report["summary"]["total_cases"], 4)
            self.assertEqual(report["summary"]["passed_cases"], 4)
            methods = {item["summary_method"] for item in report["cases"]}
            self.assertEqual(methods, {"extractive", "map_reduce"})
            for item in report["cases"]:
                self.assertEqual(item["failed_checks"], [])

    def test_quality_helpers_reject_missing_chatflow_and_summary_fields(self):
        chat_quality = evaluate_chatflow_payload(
            {
                "answer": "TLB 能缓存页表项。[L1]",
                "citations": [{"quote": "TLB 能缓存页表项。"}],
                "llm_status": "unknown",
            }
        )
        summary_quality = evaluate_summary_payload(
            {
                "content": "课程复习摘要",
                "citations": [{"file_name": "教材.md", "quote": ""}],
                "llm_status": "used",
                "summary_method": "map_reduce",
                "evidence_groups": [],
                "map_summaries": [],
            },
            expected_method="map_reduce",
        )

        self.assertFalse(chat_quality["passed"])
        self.assertIn("chatflow_web_status_known", {item["name"] for item in chat_quality["failed_checks"]})
        self.assertFalse(summary_quality["passed"])
        self.assertIn("summary_map_reduce_evidence_groups", {item["name"] for item in summary_quality["failed_checks"]})


def _write_cases(tmp: str, cases):
    path = Path(tmp) / "cases.json"
    path.write_text(json.dumps(cases, ensure_ascii=False), encoding="utf-8")
    return path


def _indexed_demo_kb(tmp: str):
    kb = CourseKnowledgeBase(Path(tmp) / "indexes")
    kb.index_text(
        "demo-operating-system",
        "os-book",
        "README.md",
        "页表记录虚拟页到物理页框的映射，用于地址转换。TLB 缓存常用页表项，减少访问页表的次数。",
    )
    kb.index_text(
        "demo-data-structures",
        "ds-stack-queue",
        "栈和队列.md",
        "栈是后进先出结构，适合函数调用和括号匹配。队列是先进先出结构，适合任务调度和广度优先搜索。",
    )
    return kb


if __name__ == "__main__":
    unittest.main()
