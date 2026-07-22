from __future__ import annotations

import json
import mimetypes
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

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
from local_course_agent.config import load_config, write_config
from local_course_agent.learning.service import (
    CourseIndexJobs,
    should_index_course_file,
)
from local_course_agent.llm import create_llm_client
from local_course_agent.ops.config_status import build_config_status
from local_course_agent.retrieval.rag import CourseKnowledgeBase
from local_course_agent.scanner import CourseCatalogCache
from local_course_agent.store import AppStore
from local_course_agent.uploads import MAX_TOTAL_UPLOAD_BYTES
from local_course_agent.web_search import create_web_search_client


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
STATIC_DIR = PROJECT_ROOT / "web" / "dist"
CONFIG_PATH = DATA_DIR / "config.json"


def resolve_static_path(request_path: str, static_dir: Path = STATIC_DIR) -> Path | None:
    parsed = urlparse(request_path)
    decoded = unquote(parsed.path).replace("\\", "/")
    parts = [part for part in decoded.split("/") if part not in ("", ".")]
    if ".." in parts:
        return None
    requested = Path(*parts) if parts else Path("index.html")
    root = static_dir.resolve()
    candidate = (root / requested).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def frontend_build_error() -> str:
    return "前端尚未构建，请运行 start.sh（macOS/Linux）或 start.bat（Windows）。"


def static_cache_control(request_path: str) -> str | None:
    path = urlparse(request_path).path
    if path in ("/", "/index.html"):
        return "no-store, max-age=0"
    if path.startswith("/assets/"):
        return "public, max-age=31536000, immutable"
    return None


def is_safe_material_root(root: Path) -> bool:
    resolved = Path(root).expanduser().resolve()
    blocked_roots = {resolved.anchor, str(DATA_DIR.resolve()), str(PROJECT_ROOT.resolve())}
    if str(resolved) in blocked_roots:
        return False
    try:
        resolved.relative_to(DATA_DIR.resolve())
        return False
    except ValueError:
        return True


def is_frontend_entry(request_path: str) -> bool:
    return urlparse(request_path).path in ("/", "/index.html")


def read_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class AppContext:
    def __init__(self):
        DATA_DIR.mkdir(exist_ok=True)
        self.store = AppStore(DATA_DIR)
        self.kb = CourseKnowledgeBase(DATA_DIR / "indexes")
        self.course_cache = CourseCatalogCache()
        self.index_jobs = CourseIndexJobs(self.kb, snapshot_path=DATA_DIR / "index_jobs.json")

    @property
    def config(self):
        config = load_config(CONFIG_PATH)
        configure = getattr(self.kb, "configure_embeddings", None)
        if callable(configure):
            configure(config.get("ai", {}))
        return config

    def root(self) -> Path | None:
        root = self.config.get("root_folder", "")
        if not root:
            return None
        return Path(root).expanduser().resolve()

    def courses(self):
        root = self.root()
        if not root:
            return []
        return self.course_cache.get(root)

    def invalidate_courses(self) -> None:
        self.course_cache.invalidate()

    def find_file(self, file_id: str) -> Path | None:
        for course in self.courses():
            found = find_file_node(course.get("children", []), file_id)
            if found:
                return Path(found["path"]).resolve()
        return None

    def find_course(self, course_id: str):
        for course in self.courses():
            if course["id"] == course_id:
                return course
        return None


def find_file_node(nodes, file_id):
    for node in nodes:
        if node["id"] == file_id and node["type"] == "file":
            return node
        if node["type"] == "folder":
            found = find_file_node(node.get("children", []), file_id)
            if found:
                return found
    return None


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
            config = CTX.config
            ai_client = create_llm_client(config.get("ai", {}))
            mineru_config = config.get("mineru", {})
            web_client = create_web_search_client(config.get("web_search", {}))
            return self.send_json(
                {
                    "root_folder": config.get("root_folder", ""),
                    "ai_provider": config.get("ai", {}).get("provider", "openai_compatible"),
                    "ai_configured": ai_client.enabled(),
                    "mineru_auto": bool(mineru_config.get("auto", True)),
                    "mineru_configured": bool(mineru_config.get("command") or mineru_config.get("token")),
                    "web_search_configured": web_client.enabled(),
                }
            )
        if parsed.path == "/api/config/status":
            return self.send_json(build_config_status(DATA_DIR, CTX.config, CTX.courses()))
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
            current = CTX.config
            root_folder = body.get("root_folder", current.get("root_folder", "")).strip()
            if not root_folder:
                return self.send_error_json("请填写资料根目录")
            root = Path(root_folder).expanduser().resolve()
            if not root.exists() or not root.is_dir():
                return self.send_error_json(f"资料根目录不存在: {root}")
            if not is_safe_material_root(root):
                return self.send_error_json("资料根目录不能设置为项目目录、数据目录或系统根目录")
            next_config = dict(current)
            next_config["root_folder"] = str(root)
            write_config(CONFIG_PATH, next_config)
            CTX.invalidate_courses()
            return self.send_json({"ok": True, "config": {"root_folder": str(root)}})
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
        path = CTX.find_file(file_id)
        if not path:
            return self.send_error_json("文件不存在", HTTPStatus.NOT_FOUND)
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.end_headers()
        with path.open("rb") as fh:
            self.wfile.write(fh.read())

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
