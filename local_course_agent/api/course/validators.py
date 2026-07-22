from __future__ import annotations

from http import HTTPStatus

from local_course_agent.api.course.errors import ApiError


def course_or_error(context, course_id: str) -> dict:
    course = context.find_course(course_id)
    if not course:
        raise ApiError("课程不存在", HTTPStatus.NOT_FOUND)
    return course


def parse_bool(value, field_name: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y"}:
            return True
        if normalized in {"false", "0", "no", "n"}:
            return False
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    raise ApiError(f"{field_name} 必须是布尔值")
