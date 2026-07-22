from __future__ import annotations

from http import HTTPStatus
from urllib.parse import parse_qs, urlparse

from local_course_agent.api.course import (
    ApiError,
    add_study_plan_item as run_add_study_plan_item,
    create_study_artifact as run_create_study_artifact,
    get_course_dashboard as run_get_course_dashboard,
    get_course_summary as run_get_course_summary,
    get_mastery as run_get_mastery,
    get_study_plan as run_get_study_plan,
    index_course as run_index_course,
    start_index_job as run_start_index_job,
    update_mastery as run_update_mastery,
    update_study_plan_item as run_update_study_plan_item,
    upload_course_files as run_upload_course_files,
)
from local_course_agent.api.router import (
    dispatch_course_action,
    match_get_course_action,
    match_post_course_action,
)
from local_course_agent.api.static import frontend_build_error, is_frontend_entry
from local_course_agent.api.system import (
    build_public_config_payload,
    build_system_status_payload,
    send_file_preview,
    update_root_folder_payload,
)


class ServerRoutesMixin:
    GET_COURSE_HANDLERS = {
        "messages": "get_course_messages",
        "memory": "get_course_memory",
        "summary": "get_course_summary",
        "quiz": "get_course_quiz",
        "notes": "get_course_notes",
        "plan": "get_study_plan",
        "dashboard": "get_course_dashboard",
        "mastery": "get_mastery",
    }
    POST_COURSE_HANDLERS = {
        "index": "index_course",
        "index_jobs": "start_index_job",
        "files": "upload_course_files",
        "chat": "post_course_chat",
        "summary": "create_course_summary",
        "quiz": "create_course_quiz",
        "notes": "add_course_note",
        "plan": "add_study_plan_item",
        "plan_item": "update_study_plan_item",
        "mastery": "update_mastery",
    }

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/config":
            return self.send_json(build_public_config_payload(self.ctx.config))
        if parsed.path == "/api/config/status":
            return self.send_json(build_system_status_payload(self.data_dir, self.ctx.config, self.ctx.courses()))
        if parsed.path == "/api/courses":
            return self.send_json({"courses": self.ctx.courses()})
        if parsed.path.startswith("/api/index-jobs/"):
            job_id = parsed.path.split("/")[-1]
            job = self.ctx.index_jobs.get(job_id)
            if not job:
                return self.send_error_json("索引任务不存在", HTTPStatus.NOT_FOUND)
            return self.send_json(job)
        course_match = match_get_course_action(self.path)
        if course_match:
            return dispatch_course_action(self, course_match, self.GET_COURSE_HANDLERS)
        if parsed.path == "/api/files/preview":
            return self.send_preview(parse_qs(parsed.query).get("id", [""])[0])
        if not (self.static_dir / "index.html").is_file():
            return self.send_error_json(frontend_build_error(), HTTPStatus.SERVICE_UNAVAILABLE)
        if is_frontend_entry(self.path):
            for header in ("If-Modified-Since", "If-None-Match"):
                if header in self.headers:
                    del self.headers[header]
        return super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/config":
            body = self.read_body()
            try:
                payload = update_root_folder_payload(
                    self.ctx.config,
                    body,
                    config_path=self.config_path,
                    project_root=self.project_root,
                    data_dir=self.data_dir,
                )
            except ApiError as exc:
                return self.send_error_json(exc.message, exc.status)
            self.ctx.invalidate_courses()
            return self.send_json(payload)
        course_match = match_post_course_action(self.path)
        if course_match:
            return dispatch_course_action(self, course_match, self.POST_COURSE_HANDLERS)
        return self.send_error_json("未知接口", HTTPStatus.NOT_FOUND)

    def get_course_messages(self, course_id: str):
        return self.send_json({"messages": self.ctx.store.list_messages(course_id)})

    def get_course_memory(self, course_id: str):
        return self.send_json({"memory": self.ctx.store.get_memory(course_id)})

    def get_course_quiz(self, course_id: str):
        return self.send_json(self.ctx.kb.generate_quiz(course_id))

    def get_course_notes(self, course_id: str):
        return self.send_json({"notes": self.ctx.store.list_notes(course_id)})

    def create_course_summary(self, course_id: str):
        return self.create_study_artifact(course_id, "summary")

    def create_course_quiz(self, course_id: str):
        return self.create_study_artifact(course_id, "quiz")

    def add_course_note(self, course_id: str):
        body = self.read_body()
        self.ctx.store.add_note(course_id, body.get("title", "学习笔记"), body.get("content", ""))
        return self.send_json({"ok": True, "notes": self.ctx.store.list_notes(course_id)})

    def index_course(self, course_id: str):
        return self.send_service_json(lambda: run_index_course(self.ctx, course_id))

    def start_index_job(self, course_id: str):
        return self.send_service_json(lambda: run_start_index_job(self.ctx, course_id), HTTPStatus.ACCEPTED)

    def create_study_artifact(self, course_id: str, artifact_type: str):
        return self.send_service_json(lambda: run_create_study_artifact(self.ctx, course_id, artifact_type))

    def get_course_summary(self, course_id: str):
        return self.send_service_json(lambda: run_get_course_summary(self.ctx, course_id))

    def upload_course_files(self, course_id: str):
        try:
            _, uploads = self.read_maybe_multipart()
        except ValueError as exc:
            return self.send_error_json(str(exc), HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        return self.send_service_json(lambda: run_upload_course_files(self.ctx, course_id, uploads))

    def get_study_plan(self, course_id: str):
        return self.send_service_json(lambda: run_get_study_plan(self.ctx, course_id))

    def get_course_dashboard(self, course_id: str):
        return self.send_service_json(lambda: run_get_course_dashboard(self.ctx, course_id))

    def get_mastery(self, course_id: str):
        return self.send_service_json(lambda: run_get_mastery(self.ctx, course_id))

    def add_study_plan_item(self, course_id: str):
        body = self.read_body()
        return self.send_service_json(lambda: run_add_study_plan_item(self.ctx, course_id, body))

    def update_study_plan_item(self, course_id: str, item_id: str):
        body = self.read_body()
        return self.send_service_json(lambda: run_update_study_plan_item(self.ctx, course_id, item_id, body))

    def update_mastery(self, course_id: str):
        body = self.read_body()
        return self.send_service_json(lambda: run_update_mastery(self.ctx, course_id, body))

    def send_preview(self, file_id: str):
        return send_file_preview(self, self.ctx, file_id)
