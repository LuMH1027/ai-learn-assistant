from __future__ import annotations

from http import HTTPStatus

from local_course_agent.api.course.errors import ApiError
from local_course_agent.api.course.validators import course_or_error, parse_bool
from local_course_agent.learning.mastery import create_knowledge_point


def get_mastery(context, course_id: str) -> dict:
    course_or_error(context, course_id)
    return {"mastery": context.store.get_mastery_state(course_id)}


def update_mastery(context, course_id: str, body: dict) -> dict:
    course_or_error(context, course_id)
    state = context.store.get_mastery_state(course_id)

    point = body.get("knowledge_point")
    updated_point = None
    if isinstance(point, dict):
        point_id = point.get("id") or point.get("point_id")
        updated_point = create_knowledge_point(
            title=point.get("title", ""),
            point_id=str(point_id) if point_id else None,
            aliases=point.get("aliases", []),
            source_refs=point.get("source_refs", []),
        )
        state = context.store.upsert_mastery_knowledge_point(
            course_id,
            updated_point,
        )

    answer = body.get("answer_result")
    if isinstance(answer, dict):
        point_id = str(answer.get("point_id") or (updated_point or {}).get("id") or "")
        if not point_id:
            raise ApiError("知识点 ID 不能为空")
        if "correct" not in answer:
            raise ApiError("答题结果不能为空")
        correct = parse_bool(answer.get("correct"), field_name="correct")
        state = context.store.apply_mastery_answer_result(
            course_id,
            point_id,
            correct=correct,
            question=str(answer.get("question") or ""),
            user_answer=str(answer.get("user_answer") or ""),
            expected_answer=str(answer.get("expected_answer") or ""),
            difficulty=str(answer.get("difficulty") or "normal"),
            confidence=answer.get("confidence"),
            source_ref=answer.get("source_ref") if isinstance(answer.get("source_ref"), dict) else None,
        )

    if not isinstance(point, dict) and not isinstance(answer, dict):
        raise ApiError("缺少 mastery 更新内容")

    return {"ok": True, "mastery": state}


def resolve_mastery_mistake(context, course_id: str, mistake_id: str) -> dict:
    course_or_error(context, course_id)
    if not str(mistake_id).strip():
        raise ApiError("错题 ID 不能为空")
    state = context.store.resolve_mastery_mistake(course_id, str(mistake_id))
    if state is None:
        raise ApiError("错题不存在", HTTPStatus.NOT_FOUND)
    return {"ok": True, "mastery": state}
