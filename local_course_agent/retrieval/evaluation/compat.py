from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from local_course_agent.retrieval.evaluation.schema import RagEvalCase
from local_course_agent.retrieval.rag import CourseKnowledgeBase


DEFAULT_SAMPLE_ROOT = Path(__file__).resolve().parents[2] / "sample_materials"
DEMO_OS_COURSE_ID = "demo-operating-system"
DEMO_DATA_STRUCTURE_COURSE_ID = "demo-data-structures"


def sample_eval_cases(course_id: str = "sample-course") -> List[RagEvalCase]:
    from local_course_agent.evaluation.demo_fixtures import sample_eval_cases as _sample_eval_cases

    return _sample_eval_cases(course_id)


def demo_eval_cases(
    os_course_id: str = DEMO_OS_COURSE_ID,
    data_structure_course_id: str = DEMO_DATA_STRUCTURE_COURSE_ID,
) -> List[RagEvalCase]:
    from local_course_agent.evaluation.demo_fixtures import demo_eval_cases as _demo_eval_cases

    return _demo_eval_cases(os_course_id, data_structure_course_id)


def index_sample_materials(
    knowledge_base: CourseKnowledgeBase,
    sample_root: Path = DEFAULT_SAMPLE_ROOT,
    os_course_id: str = DEMO_OS_COURSE_ID,
    data_structure_course_id: str = DEMO_DATA_STRUCTURE_COURSE_ID,
) -> Dict:
    from local_course_agent.evaluation.demo_fixtures import index_sample_materials as _index_sample_materials

    return _index_sample_materials(knowledge_base, sample_root, os_course_id, data_structure_course_id)


def run_demo_baseline(
    index_dir: Path,
    sample_root: Path = DEFAULT_SAMPLE_ROOT,
    strategy: str = "hybrid",
) -> Dict:
    from local_course_agent.evaluation.demo_baseline import run_demo_baseline as _run_demo_baseline

    return _run_demo_baseline(index_dir, sample_root=sample_root, strategy=strategy)


def run_chatflow_structure_eval(knowledge_base: CourseKnowledgeBase, strategy: str = "hybrid") -> Dict:
    from local_course_agent.evaluation.gates import run_chatflow_structure_eval as _run_chatflow_structure_eval

    return _run_chatflow_structure_eval(knowledge_base, strategy=strategy)


def run_summary_pipeline_eval(knowledge_base: CourseKnowledgeBase, course_names: Optional[Dict[str, str]] = None) -> Dict:
    from local_course_agent.evaluation.gates import run_summary_pipeline_eval as _run_summary_pipeline_eval

    return _run_summary_pipeline_eval(knowledge_base, course_names=course_names)


def render_markdown_report(report: Dict) -> str:
    from local_course_agent.evaluation.reports import render_markdown_report as _render_markdown_report

    return _render_markdown_report(report)


__all__ = [
    "DEFAULT_SAMPLE_ROOT",
    "DEMO_DATA_STRUCTURE_COURSE_ID",
    "DEMO_OS_COURSE_ID",
    "demo_eval_cases",
    "index_sample_materials",
    "render_markdown_report",
    "run_chatflow_structure_eval",
    "run_demo_baseline",
    "run_summary_pipeline_eval",
    "sample_eval_cases",
]
