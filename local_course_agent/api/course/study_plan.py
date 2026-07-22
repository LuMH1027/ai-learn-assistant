from __future__ import annotations

from http import HTTPStatus

from local_course_agent.api.course.errors import ApiError
from local_course_agent.api.course.validators import course_or_error
from local_course_agent.learning.service import study_plan_payload, study_plan_stats


def get_study_plan(context, course_id: str) -> dict:
    course = course_or_error(context, course_id)
    return {"plan": study_plan_payload(context.store, course_id, course)}


def add_study_plan_item(context, course_id: str, body: dict) -> dict:
    course_or_error(context, course_id)
    items = context.store.add_study_plan_item(
        course_id,
        {
            "title": body.get("title", "学习项"),
            "kind": body.get("kind", "read"),
            "status": body.get("status", "todo"),
            "estimated_minutes": body.get("estimated_minutes", 25),
        },
    )
    return {"ok": True, "plan": {"items": items, "stats": study_plan_stats(items)}}


def update_study_plan_item(context, course_id: str, item_id: str, body: dict) -> dict:
    course_or_error(context, course_id)
    try:
        parsed_item_id = int(item_id)
    except ValueError:
        raise ApiError("学习项不存在", HTTPStatus.NOT_FOUND)
    try:
        items = context.store.update_study_plan_item(course_id, parsed_item_id, body)
    except KeyError as exc:
        raise ApiError("学习项不存在", HTTPStatus.NOT_FOUND) from exc
    return {"ok": True, "plan": {"items": items, "stats": study_plan_stats(items)}}


def delete_study_plan_item(context, course_id: str, item_id: str) -> dict:
    course_or_error(context, course_id)
    try:
        parsed_item_id = int(item_id)
    except ValueError:
        raise ApiError("学习项不存在", HTTPStatus.NOT_FOUND)
    try:
        items = context.store.delete_study_plan_item(course_id, parsed_item_id)
    except KeyError as exc:
        raise ApiError("学习项不存在", HTTPStatus.NOT_FOUND) from exc
    return {"ok": True, "plan": {"items": items, "stats": study_plan_stats(items)}}
