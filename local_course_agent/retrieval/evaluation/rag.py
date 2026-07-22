from __future__ import annotations

from local_course_agent.retrieval.evaluation.compat import (
    DEFAULT_SAMPLE_ROOT,
    DEMO_DATA_STRUCTURE_COURSE_ID,
    DEMO_OS_COURSE_ID,
    demo_eval_cases,
    index_sample_materials,
    render_markdown_report,
    run_chatflow_structure_eval,
    run_demo_baseline,
    run_summary_pipeline_eval,
    sample_eval_cases,
)
from local_course_agent.retrieval.evaluation.loader import load_eval_cases
from local_course_agent.retrieval.evaluation.metrics import (
    QUALITY_ORDER,
    answer_term_coverage as _answer_term_coverage,
    rate as _rate,
    same_file as _same_file,
)
from local_course_agent.retrieval.evaluation.runner import run_rag_eval
from local_course_agent.retrieval.evaluation.schema import RagEvalCase

__all__ = [
    "DEFAULT_SAMPLE_ROOT",
    "DEMO_DATA_STRUCTURE_COURSE_ID",
    "DEMO_OS_COURSE_ID",
    "QUALITY_ORDER",
    "RagEvalCase",
    "demo_eval_cases",
    "index_sample_materials",
    "load_eval_cases",
    "render_markdown_report",
    "run_chatflow_structure_eval",
    "run_demo_baseline",
    "run_rag_eval",
    "run_summary_pipeline_eval",
    "sample_eval_cases",
]
