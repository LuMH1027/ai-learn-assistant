from __future__ import annotations

from http import HTTPStatus
import re
from urllib.parse import parse_qs, urlparse

from local_course_agent.api.course import (
    ApiError,
    create_study_artifact as run_create_study_artifact,
    get_course_dashboard as run_get_course_dashboard,
    get_course_summary as run_get_course_summary,
    get_mastery as run_get_mastery,
    index_course as run_index_course,
    start_index_job as run_start_index_job,
    update_mastery as run_update_mastery,
    upload_course_files as run_upload_course_files,
)
from local_course_agent.api.course.mastery import resolve_mastery_mistake as run_resolve_mastery_mistake
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
        "note": "update_course_note",
        "delete_note": "delete_course_note",
        "clear_memory": "clear_course_memory",
        "mastery": "update_mastery",
        "resolve_mastery_mistake": "resolve_mastery_mistake",
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
        conversation_match = match_conversation_route(parsed.path)
        if conversation_match:
            course_id, conversation_id, action = conversation_match
            if conversation_id is None and action == "":
                return self.list_course_conversations(course_id)
            if conversation_id is not None and action == "messages":
                return self.get_conversation_messages(course_id, conversation_id)
            if conversation_id is not None and action == "memory":
                return self.get_conversation_memory(course_id, conversation_id)
            return self.send_error_json("未知对话接口", HTTPStatus.NOT_FOUND)
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
        conversation_match = match_conversation_route(parsed.path)
        if conversation_match:
            course_id, conversation_id, action = conversation_match
            if conversation_id is None and action == "":
                return self.create_course_conversation(course_id)
            if conversation_id is not None and action == "":
                return self.update_course_conversation(course_id, conversation_id)
            if conversation_id is not None and action == "delete":
                return self.delete_course_conversation(course_id, conversation_id)
            if conversation_id is not None and action == "read":
                return self.mark_conversation_read(course_id, conversation_id)
            if conversation_id is not None and action == "chat":
                return self.post_conversation_chat(course_id, conversation_id)
            if conversation_id is not None and action in {"summary", "quiz"}:
                return self.create_study_artifact(course_id, action, conversation_id=conversation_id)
            if conversation_id is not None and action == "memory/clear":
                return self.clear_course_memory(course_id, conversation_id=conversation_id)
            return self.send_error_json("未知对话接口", HTTPStatus.NOT_FOUND)
        if course_match:
            return dispatch_course_action(self, course_match, self.POST_COURSE_HANDLERS)
        return self.send_error_json("未知接口", HTTPStatus.NOT_FOUND)

    def get_course_messages(self, course_id: str):
        return self.send_json({"messages": self.ctx.store.list_messages(course_id)})

    def get_course_memory(self, course_id: str):
        return self.send_json({"memory": self.ctx.store.get_memory(course_id)})

    def list_course_conversations(self, course_id: str):
        return self.send_json({"conversations": self.ctx.store.list_conversations(course_id)})

    def create_course_conversation(self, course_id: str):
        body = self.read_body()
        conversation = self.ctx.store.create_conversation(course_id, body.get("title"))
        return self.send_json({"ok": True, "conversation": conversation, "conversations": self.ctx.store.list_conversations(course_id)})

    def update_course_conversation(self, course_id: str, conversation_id: str):
        body = self.read_body()
        try:
            conversation = self.ctx.store.update_conversation(course_id, conversation_id, body)
        except KeyError:
            return self.send_error_json("对话不存在", HTTPStatus.NOT_FOUND)
        return self.send_json({"ok": True, "conversation": conversation, "conversations": self.ctx.store.list_conversations(course_id)})

    def delete_course_conversation(self, course_id: str, conversation_id: str):
        try:
            conversations = self.ctx.store.delete_conversation(course_id, conversation_id)
        except KeyError:
            return self.send_error_json("对话不存在", HTTPStatus.NOT_FOUND)
        return self.send_json({"ok": True, "conversations": conversations})

    def mark_conversation_read(self, course_id: str, conversation_id: str):
        try:
            conversation = self.ctx.store.mark_conversation_read(course_id, conversation_id)
        except KeyError:
            return self.send_error_json("对话不存在", HTTPStatus.NOT_FOUND)
        return self.send_json({"ok": True, "conversation": conversation, "conversations": self.ctx.store.list_conversations(course_id)})

    def get_conversation_messages(self, course_id: str, conversation_id: str):
        try:
            messages = self.ctx.store.list_messages(course_id, conversation_id)
            self.ctx.store.mark_conversation_read(course_id, conversation_id)
        except KeyError:
            return self.send_error_json("对话不存在", HTTPStatus.NOT_FOUND)
        return self.send_json({"messages": messages})

    def get_conversation_memory(self, course_id: str, conversation_id: str):
        try:
            memory = self.ctx.store.get_memory(course_id, conversation_id)
        except KeyError:
            return self.send_error_json("对话不存在", HTTPStatus.NOT_FOUND)
        return self.send_json({"memory": memory})

    def post_conversation_chat(self, course_id: str, conversation_id: str):
        self.conversation_id = conversation_id
        try:
            return self.post_course_chat(course_id)
        finally:
            self.conversation_id = None

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

    def update_course_note(self, course_id: str, note_id: str):
        body = self.read_body()
        note = self.ctx.store.update_note(course_id, note_id, body)
        if note is None:
            return self.send_error_json("笔记不存在", HTTPStatus.NOT_FOUND)
        return self.send_json({"ok": True, "note": note, "notes": self.ctx.store.list_notes(course_id)})

    def delete_course_note(self, course_id: str, note_id: str):
        if not self.ctx.store.delete_note(course_id, note_id):
            return self.send_error_json("笔记不存在", HTTPStatus.NOT_FOUND)
        return self.send_json({"ok": True, "notes": self.ctx.store.list_notes(course_id)})

    def clear_course_memory(self, course_id: str, conversation_id: str | None = None):
        messages = self.ctx.store.clear_messages(course_id, conversation_id)
        memory = self.ctx.store.clear_memory(course_id, conversation_id)
        return self.send_json({"ok": True, "messages": messages, "memory": memory})

    def index_course(self, course_id: str):
        return self.send_service_json(lambda: run_index_course(self.ctx, course_id))

    def start_index_job(self, course_id: str):
        return self.send_service_json(lambda: run_start_index_job(self.ctx, course_id), HTTPStatus.ACCEPTED)

    def create_study_artifact(self, course_id: str, artifact_type: str, conversation_id: str | None = None):
        return self.send_service_json(lambda: run_create_study_artifact(self.ctx, course_id, artifact_type, conversation_id=conversation_id))

    def get_course_summary(self, course_id: str):
        return self.send_service_json(lambda: run_get_course_summary(self.ctx, course_id))

    def upload_course_files(self, course_id: str):
        try:
            _, uploads = self.read_maybe_multipart()
        except ValueError as exc:
            return self.send_error_json(str(exc), HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        return self.send_service_json(lambda: run_upload_course_files(self.ctx, course_id, uploads))

    def get_course_dashboard(self, course_id: str):
        return self.send_service_json(lambda: run_get_course_dashboard(self.ctx, course_id))

    def get_mastery(self, course_id: str):
        return self.send_service_json(lambda: run_get_mastery(self.ctx, course_id))

    def update_mastery(self, course_id: str):
        body = self.read_body()
        return self.send_service_json(lambda: run_update_mastery(self.ctx, course_id, body))

    def resolve_mastery_mistake(self, course_id: str, mistake_id: str):
        return self.send_service_json(lambda: run_resolve_mastery_mistake(self.ctx, course_id, mistake_id))

    def send_preview(self, file_id: str):
        return send_file_preview(self, self.ctx, file_id)


def match_conversation_route(path: str) -> tuple[str, str | None, str] | None:
    base = re.fullmatch(r"/api/courses/([^/]+)/conversations/?", path)
    if base:
        from urllib.parse import unquote
        return unquote(base.group(1)), None, ""
    match = re.fullmatch(r"/api/courses/([^/]+)/conversations/([^/]+)(?:/(.*))?", path)
    if not match:
        return None
    from urllib.parse import unquote
    return unquote(match.group(1)), unquote(match.group(2)), match.group(3) or ""
