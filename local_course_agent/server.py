from __future__ import annotations

from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from local_course_agent.api.chat import (
    CLARIFICATION_ANSWER,
    ChatFlow,
    ChatFlowError,
    emit_stream_text,
    index_chat_uploads as run_index_chat_uploads,
    retrieve_web_sources as run_retrieve_web_sources,
    synthesize_answer as run_synthesize_answer,
    synthesize_answer_stream as run_synthesize_answer_stream,
)
from local_course_agent.api.course import (
    ApiError,
    add_study_plan_item as run_add_study_plan_item,
    course_index_stats,
    create_study_artifact as run_create_study_artifact,
    get_course_dashboard as run_get_course_dashboard,
    get_course_summary as run_get_course_summary,
    get_mastery as run_get_mastery,
    get_study_plan as run_get_study_plan,
    index_course as run_index_course,
    start_index_job as run_start_index_job,
    update_study_plan_item as run_update_study_plan_item,
    update_mastery as run_update_mastery,
    upload_course_files as run_upload_course_files,
)
from local_course_agent.api.context import (
    CONFIG_PATH,
    DATA_DIR,
    PROJECT_ROOT,
    STATIC_DIR,
    AppContext,
    find_file_node,
    is_safe_material_root,
    read_json,
    write_json,
)
from local_course_agent.api.http import (
    ClientDisconnected,
    begin_chunked_stream,
    error_payload,
    read_json_body,
    read_request_payload,
    send_json_response,
    write_stream_end,
    write_stream_event,
)
from local_course_agent.api.router import (
    dispatch_course_action,
    match_get_course_action,
    match_post_course_action,
    parse_course_route,
)
from local_course_agent.api.static import (
    frontend_build_error,
    is_frontend_entry,
    resolve_static_path,
    static_cache_control,
)
from local_course_agent.api.system import (
    build_public_config_payload,
    build_system_status_payload,
    send_file_preview,
    update_root_folder_payload,
)
from local_course_agent.learning.service import should_index_course_file
from local_course_agent.uploads import MAX_TOTAL_UPLOAD_BYTES


CTX = AppContext()


class Handler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
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

    def translate_path(self, path):
        resolved = resolve_static_path(path)
        return str(resolved if resolved is not None else STATIC_DIR / "__invalid__")

    def end_headers(self):
        cache_control = static_cache_control(self.path)
        if cache_control:
            self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/config":
            return self.send_json(build_public_config_payload(CTX.config))
        if parsed.path == "/api/config/status":
            return self.send_json(build_system_status_payload(DATA_DIR, CTX.config, CTX.courses()))
        if parsed.path == "/api/courses":
            return self.send_json({"courses": CTX.courses()})
        if parsed.path.startswith("/api/index-jobs/"):
            job_id = parsed.path.split("/")[-1]
            job = CTX.index_jobs.get(job_id)
            if not job:
                return self.send_error_json("索引任务不存在", HTTPStatus.NOT_FOUND)
            return self.send_json(job)
        course_match = match_get_course_action(self.path)
        if course_match:
            return dispatch_course_action(self, course_match, self.GET_COURSE_HANDLERS)
        if parsed.path == "/api/files/preview":
            return self.send_preview(parse_qs(parsed.query).get("id", [""])[0])
        if not (STATIC_DIR / "index.html").is_file():
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
                    CTX.config,
                    body,
                    config_path=CONFIG_PATH,
                    project_root=PROJECT_ROOT,
                    data_dir=DATA_DIR,
                )
            except ApiError as exc:
                return self.send_error_json(exc.message, exc.status)
            CTX.invalidate_courses()
            return self.send_json(payload)
        course_match = match_post_course_action(self.path)
        if course_match:
            return dispatch_course_action(self, course_match, self.POST_COURSE_HANDLERS)
        return self.send_error_json("未知接口", HTTPStatus.NOT_FOUND)

    def get_course_messages(self, course_id: str):
        return self.send_json({"messages": CTX.store.list_messages(course_id)})

    def get_course_memory(self, course_id: str):
        return self.send_json({"memory": CTX.store.get_memory(course_id)})

    def get_course_quiz(self, course_id: str):
        return self.send_json(CTX.kb.generate_quiz(course_id))

    def get_course_notes(self, course_id: str):
        return self.send_json({"notes": CTX.store.list_notes(course_id)})

    def post_course_chat(self, course_id: str):
        accept = self.headers.get("Accept", "")
        stream_format = (
            "sse" if "text/event-stream" in accept
            else "ndjson" if "application/x-ndjson" in accept
            else None
        )
        try:
            return self.chat(course_id, stream=stream_format)
        except ClientDisconnected:
            return None

    def create_course_summary(self, course_id: str):
        return self.create_study_artifact(course_id, "summary")

    def create_course_quiz(self, course_id: str):
        return self.create_study_artifact(course_id, "quiz")

    def add_course_note(self, course_id: str):
        body = self.read_body()
        CTX.store.add_note(course_id, body.get("title", "学习笔记"), body.get("content", ""))
        return self.send_json({"ok": True, "notes": CTX.store.list_notes(course_id)})

    def index_course(self, course_id: str):
        return self.send_service_json(lambda: run_index_course(CTX, course_id))

    def start_index_job(self, course_id: str):
        return self.send_service_json(lambda: run_start_index_job(CTX, course_id), HTTPStatus.ACCEPTED)

    def chat(self, course_id: str, stream=False):
        try:
            body, uploads = self.read_maybe_multipart()
        except ValueError as exc:
            return self.send_error_json(str(exc), HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        if not str(body.get("question", "")).strip() and not uploads:
            return self.send_error_json("问题不能为空")
        if stream:
            emit = lambda event: self.send_stream_event(event, stream)
        else:
            emit = lambda _event: None
        if stream:
            self.begin_stream(stream)
            emit(
                {
                    "type": "status",
                    "stage": "accepted",
                    "detail": "已收到问题，正在准备…",
                }
            )
        try:
            payload = ChatFlow(
                context=CTX,
                data_dir=DATA_DIR,
                emit=emit,
                stream_format=stream,
                index_uploads=self.index_chat_uploads,
                retrieve_web=self.retrieve_web_sources,
                synthesize=self.synthesize_answer,
                synthesize_stream=self.synthesize_answer_stream,
            ).run(course_id, body, uploads)
        except ChatFlowError as exc:
            if stream:
                emit({"type": "error", "error": str(exc)})
                self.end_stream()
                return None
            return self.send_error_json(str(exc))
        if stream:
            emit({"type": "done", "result": payload})
            self.end_stream()
            return None
        return self.send_json(payload)

    def retrieve_web_sources(self, question: str, result: dict, web_config=None, allow_web=True):
        return run_retrieve_web_sources(question, result, web_config, allow_web)

    def create_study_artifact(self, course_id: str, artifact_type: str):
        return self.send_service_json(lambda: run_create_study_artifact(CTX, course_id, artifact_type))

    def get_course_summary(self, course_id: str):
        return self.send_service_json(lambda: run_get_course_summary(CTX, course_id))

    def upload_course_files(self, course_id: str):
        try:
            _, uploads = self.read_maybe_multipart()
        except ValueError as exc:
            return self.send_error_json(str(exc), HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        return self.send_service_json(lambda: run_upload_course_files(CTX, course_id, uploads))

    def get_study_plan(self, course_id: str):
        return self.send_service_json(lambda: run_get_study_plan(CTX, course_id))

    def get_course_dashboard(self, course_id: str):
        return self.send_service_json(lambda: run_get_course_dashboard(CTX, course_id))

    def get_mastery(self, course_id: str):
        return self.send_service_json(lambda: run_get_mastery(CTX, course_id))

    def add_study_plan_item(self, course_id: str):
        body = self.read_body()
        return self.send_service_json(lambda: run_add_study_plan_item(CTX, course_id, body))

    def update_study_plan_item(self, course_id: str, item_id: str):
        body = self.read_body()
        return self.send_service_json(lambda: run_update_study_plan_item(CTX, course_id, item_id, body))

    def update_mastery(self, course_id: str):
        body = self.read_body()
        return self.send_service_json(lambda: run_update_mastery(CTX, course_id, body))

    def index_chat_uploads(self, course_id: str, uploads: list):
        return run_index_chat_uploads(CTX, DATA_DIR, course_id, uploads)

    def synthesize_answer(self, question: str, result: dict, image_paths=None, ai_config=None):
        return run_synthesize_answer(
            question,
            result,
            image_paths=image_paths,
            ai_config=ai_config if ai_config is not None else CTX.config.get("ai", {}),
        )

    def synthesize_answer_stream(
        self,
        question: str,
        result: dict,
        emit_delta,
        image_paths=None,
        ai_config=None,
    ):
        return run_synthesize_answer_stream(
            question,
            result,
            emit_delta=emit_delta,
            image_paths=image_paths,
            ai_config=ai_config if ai_config is not None else CTX.config.get("ai", {}),
        )

    def send_preview(self, file_id: str):
        return send_file_preview(self, CTX, file_id)

    def read_body(self):
        return read_json_body(self.headers, self.rfile)

    def read_maybe_multipart(self):
        return read_request_payload(
            self.headers,
            self.rfile,
            max_total_upload_bytes=MAX_TOTAL_UPLOAD_BYTES,
        )

    def send_service_json(self, action, status=HTTPStatus.OK):
        try:
            payload = action()
        except ApiError as exc:
            return self.send_error_json(exc.message, exc.status)
        return self.send_json(payload, status)

    def send_json(self, payload, status=HTTPStatus.OK):
        send_json_response(self, payload, status)

    def begin_stream(self, stream_format="sse"):
        begin_chunked_stream(self, stream_format)

    def send_stream_event(self, event, stream_format="sse"):
        return write_stream_event(self.wfile, event, stream_format)

    def end_stream(self):
        return write_stream_end(self.wfile)

    def send_error_json(self, message, status=HTTPStatus.BAD_REQUEST):
        return self.send_json(error_payload(message), status)


def main():
    STATIC_DIR.mkdir(exist_ok=True)
    port = 8000
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Local Course Agent running at http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
