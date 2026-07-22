from __future__ import annotations

from local_course_agent.api.course.stats import course_index_stats
from local_course_agent.api.course.validators import course_or_error
from local_course_agent.learning.dashboard import build_course_dashboard


def get_course_dashboard(context, course_id: str) -> dict:
    course = course_or_error(context, course_id)
    return {
        "dashboard": build_course_dashboard(
            course=course,
            messages=context.store.list_messages(course_id),
            notes=context.store.list_notes(course_id),
            study_plan=context.store.list_study_plan(course_id),
            mastery_state=context.store.get_mastery_state(course_id),
            index_stats=course_index_stats(context.kb, course_id),
        )
    }
