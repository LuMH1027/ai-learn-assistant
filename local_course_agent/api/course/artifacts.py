from __future__ import annotations

from local_course_agent.api.course.validators import course_or_error
from local_course_agent.learning.service import (
    create_study_artifact as create_study_artifact_payload,
    generate_course_summary,
)


def create_study_artifact(context, course_id: str, artifact_type: str, conversation_id: str | None = None) -> dict:
    course = course_or_error(context, course_id)
    return create_study_artifact_payload(
        context.kb,
        context.store,
        context.courses,
        course,
        course_id,
        artifact_type,
        conversation_id=conversation_id,
        invalidate=context.invalidate_courses,
        ai_config=context.config.get("ai", {}),
    )


def get_course_summary(context, course_id: str) -> dict:
    course = context.find_course(course_id) or {"name": ""}
    return generate_course_summary(
        context.kb,
        course_id,
        course.get("name", ""),
        ai_config=context.config.get("ai", {}),
    )
