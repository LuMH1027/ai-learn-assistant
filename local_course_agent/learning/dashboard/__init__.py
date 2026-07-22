from __future__ import annotations

from local_course_agent.learning.dashboard.activity import file_activity, recent_activity
from local_course_agent.learning.dashboard.mastery import mastery_item_summary, mastery_summary
from local_course_agent.learning.dashboard.materials import (
    GENERATED_FOLDER,
    generated_artifacts,
    is_generated_file,
    iter_files,
    materials_stats,
    split_course_files,
)
from local_course_agent.learning.dashboard.progress import (
    learning_progress,
    next_plan_item,
    plan_item_summary,
    review_queue,
)
from local_course_agent.learning.dashboard.utils import compact, int_value, is_due, status_rank, strip_sort_key, time_key


def build_course_dashboard(
    course: dict,
    messages: list[dict] | None = None,
    notes: list[dict] | None = None,
    study_plan: list[dict] | None = None,
    mastery_state: dict | None = None,
    index_stats: dict | None = None,
    timestamp: str | None = None,
) -> dict:
    """Build a side-effect-free dashboard payload for one course."""

    messages = list(messages or [])
    notes = list(notes or [])
    study_plan = list(study_plan or [])
    index_stats = dict(index_stats or {})
    mastery = mastery_summary(mastery_state, timestamp=timestamp)
    material_files, generated_files = split_course_files(course)
    progress = learning_progress(study_plan)
    return {
        "course": {
            "id": course.get("id", ""),
            "name": course.get("name", ""),
            "path": course.get("path", ""),
        },
        "learning_progress": progress,
        "recent_activity": recent_activity(messages, notes, study_plan, generated_files),
        "materials": materials_stats(material_files, generated_files, index_stats),
        "review_queue": review_queue(study_plan),
        "mastery": mastery,
        "generated_artifacts": generated_artifacts(generated_files),
    }


# Backward-compatible private names for tests or integrations that reached into this module.
_learning_progress = learning_progress
_materials_stats = materials_stats
_review_queue = review_queue
_mastery_summary = mastery_summary
_mastery_item_summary = mastery_item_summary
_generated_artifacts = generated_artifacts
_recent_activity = recent_activity
_next_plan_item = next_plan_item
_plan_item_summary = plan_item_summary
_file_activity = file_activity
_iter_files = iter_files
_is_generated_file = is_generated_file
_status_rank = status_rank
_time_key = time_key
_is_due = is_due
_compact = compact
_strip_sort_key = strip_sort_key
_int = int_value
