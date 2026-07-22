from __future__ import annotations

import json
from http import HTTPStatus
from pathlib import Path

from local_course_agent.learning.dashboard import build_course_dashboard
from local_course_agent.learning.service import (
    build_course_index,
    create_study_artifact as create_study_artifact_payload,
    generate_course_summary,
    study_plan_payload,
    study_plan_stats,
)
from local_course_agent.uploads import save_course_upload


class ApiError(Exception):
    def __init__(self, message: str, status=HTTPStatus.BAD_REQUEST):
        super().__init__(message)
        self.message = message
        self.status = status


def index_course(context, course_id: str) -> dict:
    course = _course_or_error(context, course_id)
    return build_course_index(context.kb, course, course_id, mineru_config=context.config.get("mineru", {}))


def start_index_job(context, course_id: str) -> dict:
    course = _course_or_error(context, course_id)
    return context.index_jobs.start(course_id, course, mineru_config=context.config.get("mineru", {}))


def create_study_artifact(context, course_id: str, artifact_type: str) -> dict:
    course = _course_or_error(context, course_id)
    return create_study_artifact_payload(
        context.kb,
        context.store,
        context.courses,
        course,
        course_id,
        artifact_type,
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


def upload_course_files(context, course_id: str, uploads: list) -> dict:
    course = _course_or_error(context, course_id)
    if not uploads:
        raise ApiError("没有收到文件")
    saved = []
    for upload in uploads:
        try:
            path = save_course_upload(Path(course["path"]), upload["filename"], upload["content"])
        except ValueError as exc:
            raise ApiError(str(exc)) from exc
        saved.append({"name": path.name, "path": str(path)})
    context.invalidate_courses()
    return {"ok": True, "saved": saved, "courses": context.courses()}


def get_study_plan(context, course_id: str) -> dict:
    course = _course_or_error(context, course_id)
    return {"plan": study_plan_payload(context.store, course_id, course)}


def get_course_dashboard(context, course_id: str) -> dict:
    course = _course_or_error(context, course_id)
    return {
        "dashboard": build_course_dashboard(
            course=course,
            messages=context.store.list_messages(course_id),
            notes=context.store.list_notes(course_id),
            study_plan=context.store.list_study_plan(course_id),
            index_stats=course_index_stats(context.kb, course_id),
        )
    }


def add_study_plan_item(context, course_id: str, body: dict) -> dict:
    _course_or_error(context, course_id)
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
    _course_or_error(context, course_id)
    try:
        parsed_item_id = int(item_id)
    except ValueError:
        raise ApiError("学习项不存在", HTTPStatus.NOT_FOUND)
    try:
        items = context.store.update_study_plan_item(course_id, parsed_item_id, body)
    except KeyError as exc:
        raise ApiError("学习项不存在", HTTPStatus.NOT_FOUND) from exc
    return {"ok": True, "plan": {"items": items, "stats": study_plan_stats(items)}}


def course_index_stats(kb, course_id: str) -> dict:
    path_factory = getattr(kb, "_path", None)
    path = path_factory(course_id) if callable(path_factory) else None
    if not path:
        storage_dir = getattr(kb, "storage_dir", None)
        path = Path(storage_dir) / f"{course_id}.json" if storage_dir else None
    if not path or not Path(path).exists():
        return {"indexed_files": 0, "total_chunks": 0}
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"indexed_files": 0, "total_chunks": 0}
    if isinstance(payload, dict):
        chunks = payload.get("chunks", [])
        stats = {
            "schema_version": payload.get("schema_version"),
            "tokenizer_version": payload.get("tokenizer_version", ""),
        }
    elif isinstance(payload, list):
        chunks = payload
        stats = {"schema_version": None, "tokenizer_version": ""}
    else:
        chunks = []
        stats = {"schema_version": None, "tokenizer_version": ""}
    if not isinstance(chunks, list):
        chunks = []
    file_keys = {
        str(chunk.get("file_id") or chunk.get("file_name") or "")
        for chunk in chunks
        if isinstance(chunk, dict) and (chunk.get("file_id") or chunk.get("file_name"))
    }
    stats.update({"indexed_files": len(file_keys), "total_chunks": len(chunks)})
    return stats


def _course_or_error(context, course_id: str) -> dict:
    course = context.find_course(course_id)
    if not course:
        raise ApiError("课程不存在", HTTPStatus.NOT_FOUND)
    return course
