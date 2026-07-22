from __future__ import annotations

from pathlib import Path

from local_course_agent.api.course.errors import ApiError
from local_course_agent.api.course.validators import course_or_error
from local_course_agent.uploads import save_course_upload


def upload_course_files(context, course_id: str, uploads: list) -> dict:
    course = course_or_error(context, course_id)
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
