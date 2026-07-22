from __future__ import annotations

from local_course_agent.api.course.validators import course_or_error
from local_course_agent.learning.service import build_course_index


def index_course(context, course_id: str) -> dict:
    course = course_or_error(context, course_id)
    return build_course_index(context.kb, course, course_id, mineru_config=context.config.get("mineru", {}))


def start_index_job(context, course_id: str) -> dict:
    course = course_or_error(context, course_id)
    return context.index_jobs.start(course_id, course, mineru_config=context.config.get("mineru", {}))
