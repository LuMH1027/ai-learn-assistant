from __future__ import annotations

from pathlib import Path
from typing import Dict

from local_course_agent.evaluation.demo_fixtures import (
    DEFAULT_SAMPLE_ROOT,
    DEMO_DATA_STRUCTURE_COURSE_ID,
    DEMO_OS_COURSE_ID,
    demo_eval_cases,
    index_sample_materials,
)
from local_course_agent.evaluation.gates import run_chatflow_structure_eval, run_summary_pipeline_eval
from local_course_agent.retrieval.rag import CourseKnowledgeBase
from local_course_agent.retrieval.rag_eval import run_rag_eval


def run_demo_baseline(
    index_dir: Path,
    sample_root: Path = DEFAULT_SAMPLE_ROOT,
    strategy: str = "hybrid",
) -> Dict:
    knowledge_base = CourseKnowledgeBase(Path(index_dir))
    manifest = index_sample_materials(knowledge_base, Path(sample_root))
    cases = demo_eval_cases()
    report = run_rag_eval(knowledge_base, cases, strategy=strategy)
    chatflow_eval = run_chatflow_structure_eval(knowledge_base, strategy=strategy)
    summary_eval = run_summary_pipeline_eval(
        knowledge_base,
        course_names={
            DEMO_OS_COURSE_ID: "操作系统",
            DEMO_DATA_STRUCTURE_COURSE_ID: "数据结构",
        },
    )
    chatflow_summary = chatflow_eval["summary"]
    summary_quality = summary_eval["summary"]
    report["chatflow_eval"] = chatflow_eval
    report["summary_eval"] = summary_eval
    report["summary"].update(
        {
            "chatflow_structure_pass_rate": chatflow_summary["pass_rate"],
            "summary_pipeline_pass_rate": summary_quality["pass_rate"],
            "quality_gate_passed": (
                report["summary"]["passed_cases"] == report["summary"]["total_cases"]
                and chatflow_summary["passed_cases"] == chatflow_summary["total_cases"]
                and summary_quality["passed_cases"] == summary_quality["total_cases"]
            ),
        }
    )
    report["baseline"] = {
        "name": "sample_materials demo baseline",
        "sample_root": manifest["sample_root"],
        "course_ids": manifest["course_ids"],
        "indexed_files": len(manifest["indexed_files"]),
        "missing_files": manifest["missing_files"],
        "case_ids": [case.id for case in cases],
    }
    return report
