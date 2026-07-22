from __future__ import annotations

from pathlib import Path

from local_course_agent.learning import artifacts as _artifacts
from local_course_agent.learning import study_plan as _study_plan
from local_course_agent.learning.files import iter_files, save_study_artifact, should_index_course_file
from local_course_agent.learning.indexing import (
    CourseIndexJobs as _BaseCourseIndexJobs,
    build_course_index as _build_course_index,
    emit_progress as _emit_progress,
    index_job_file_payload as _index_job_file_payload,
    timestamp_now as _timestamp_now,
)
from local_course_agent.llm.config import create_llm_client
from local_course_agent.parser import extract_text

PLAN_FILE_LIMIT = _study_plan.PLAN_FILE_LIMIT


def build_course_index(kb, course: dict, course_id: str, mineru_config=None, progress_callback=None) -> dict:
    return _build_course_index(
        kb,
        course,
        course_id,
        mineru_config=mineru_config,
        progress_callback=progress_callback,
        extract_text_fn=extract_text,
    )


def emit_progress(progress_callback, **changes) -> None:
    return _emit_progress(progress_callback, **changes)


def index_job_file_payload(file_node: dict) -> dict:
    return _index_job_file_payload(file_node)


class CourseIndexJobs(_BaseCourseIndexJobs):
    def __init__(self, kb, max_workers: int = 1, snapshot_path: Path | str | None = Path("data/index_jobs.json")):
        super().__init__(
            kb,
            max_workers=max_workers,
            snapshot_path=snapshot_path,
            build_index=build_course_index,
        )


def timestamp_now() -> str:
    return _timestamp_now()


def create_study_artifact(
    kb,
    store,
    courses_provider,
    course: dict,
    course_id: str,
    artifact_type: str,
    invalidate=None,
    ai_config=None,
) -> dict:
    return _artifacts.create_study_artifact(
        kb,
        store,
        courses_provider,
        course,
        course_id,
        artifact_type,
        invalidate=invalidate,
        ai_config=ai_config,
        summary_builder=generate_course_summary,
    )


def generate_course_summary(kb, course_id: str, course_name: str = "", ai_config=None, limit: int = 8) -> dict:
    return _artifacts.generate_course_summary(
        kb,
        course_id,
        course_name,
        ai_config=ai_config,
        limit=limit,
        create_client=create_llm_client,
    )


def build_default_study_plan(course: dict) -> list[dict]:
    return _study_plan.build_default_study_plan(course)


def study_plan_file_rank(file_node: dict) -> tuple[int, str]:
    return _study_plan.study_plan_file_rank(file_node)


def study_plan_item_from_file(file_node: dict) -> tuple[str, str, int]:
    return _study_plan.study_plan_item_from_file(file_node)


def study_plan_stats(items: list[dict]) -> dict:
    return _study_plan.study_plan_stats(items)


def study_plan_payload(store, course_id: str, course: dict) -> dict:
    return _study_plan.study_plan_payload(store, course_id, course, plan_builder=build_default_study_plan)


__all__ = [
    "PLAN_FILE_LIMIT",
    "CourseIndexJobs",
    "build_course_index",
    "build_default_study_plan",
    "create_llm_client",
    "create_study_artifact",
    "emit_progress",
    "extract_text",
    "generate_course_summary",
    "index_job_file_payload",
    "iter_files",
    "save_study_artifact",
    "should_index_course_file",
    "study_plan_file_rank",
    "study_plan_item_from_file",
    "study_plan_payload",
    "study_plan_stats",
    "timestamp_now",
]
