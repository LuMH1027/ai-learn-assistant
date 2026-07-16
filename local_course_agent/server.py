from __future__ import annotations

import json
import mimetypes
import cgi
from datetime import datetime
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from local_course_agent.agent_strategy import build_agent_trace
from local_course_agent.config import load_config, write_config
from local_course_agent.llm import build_grounded_prompt, create_llm_client
from local_course_agent.parser import extract_text
from local_course_agent.rag import CourseKnowledgeBase
from local_course_agent.scanner import CourseScanner, is_image_file, stable_id
from local_course_agent.store import AppStore
from local_course_agent.uploads import save_chat_upload, save_course_upload
from local_course_agent.web_search import (
    WebSearchError,
    create_web_search_client,
    should_search_web,
)


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

    @property
    def config(self):
        return load_config(CONFIG_PATH)

    def root(self) -> Path | None:
        root = self.config.get("root_folder", "")
        if not root:
            return None
        return Path(root).expanduser().resolve()

    def courses(self):
        root = self.root()
        if not root:
            return []
        return CourseScanner(root).scan()

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

    def translate_path(self, path):
        resolved = resolve_static_path(path)
        return str(resolved if resolved is not None else STATIC_DIR / "__invalid__")

    def end_headers(self):
        cache_control = static_cache_control(self.path)
        if cache_control:
            self.send_header("Cache-Control", cache_control)
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
        if parsed.path == "/api/courses":
            return self.send_json({"courses": CTX.courses()})
        if parsed.path.startswith("/api/courses/") and parsed.path.endswith("/messages"):
            course_id = parsed.path.split("/")[3]
            return self.send_json({"messages": CTX.store.list_messages(course_id)})
        if parsed.path.startswith("/api/courses/") and parsed.path.endswith("/memory"):
            course_id = parsed.path.split("/")[3]
            return self.send_json({"memory": CTX.store.get_memory(course_id)})
        if parsed.path.startswith("/api/courses/") and parsed.path.endswith("/summary"):
            course_id = parsed.path.split("/")[3]
            return self.send_json(CTX.kb.generate_summary(course_id))
        if parsed.path.startswith("/api/courses/") and parsed.path.endswith("/quiz"):
            course_id = parsed.path.split("/")[3]
            return self.send_json(CTX.kb.generate_quiz(course_id))
        if parsed.path.startswith("/api/courses/") and parsed.path.endswith("/notes"):
            course_id = parsed.path.split("/")[3]
            return self.send_json({"notes": CTX.store.list_notes(course_id)})
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
            next_config = dict(current)
            next_config["root_folder"] = str(root)
            write_config(CONFIG_PATH, next_config)
            return self.send_json({"ok": True, "config": {"root_folder": str(root)}})
        if parsed.path.startswith("/api/courses/") and parsed.path.endswith("/index"):
            course_id = parsed.path.split("/")[3]
            return self.index_course(course_id)
        if parsed.path.startswith("/api/courses/") and parsed.path.endswith("/files"):
            course_id = parsed.path.split("/")[3]
            return self.upload_course_files(course_id)
        if parsed.path.startswith("/api/courses/") and parsed.path.endswith("/chat"):
            course_id = parsed.path.split("/")[3]
            accept = self.headers.get("Accept", "")
            stream_format = (
                "sse" if "text/event-stream" in accept
                else "ndjson" if "application/x-ndjson" in accept
                else None
            )
            return self.chat(course_id, stream=stream_format)
        if parsed.path.startswith("/api/courses/") and parsed.path.endswith("/summary"):
            course_id = parsed.path.split("/")[3]
            return self.create_study_artifact(course_id, "summary")
        if parsed.path.startswith("/api/courses/") and parsed.path.endswith("/quiz"):
            course_id = parsed.path.split("/")[3]
            return self.create_study_artifact(course_id, "quiz")
        if parsed.path.startswith("/api/courses/") and parsed.path.endswith("/notes"):
            course_id = parsed.path.split("/")[3]
            body = self.read_body()
            CTX.store.add_note(course_id, body.get("title", "学习笔记"), body.get("content", ""))
            return self.send_json({"ok": True, "notes": CTX.store.list_notes(course_id)})
        return self.send_error_json("未知接口", HTTPStatus.NOT_FOUND)

    def index_course(self, course_id: str):
        course = CTX.find_course(course_id)
        if not course:
            return self.send_error_json("课程不存在", HTTPStatus.NOT_FOUND)
        CTX.kb.clear_course(course_id)
        indexed_files = 0
        indexed_chunks = 0
        config = CTX.config
        for file_node in iter_files(course.get("children", [])):
            path = Path(file_node["path"])
            if not should_index_course_file(course["path"], path):
                continue
            for page in extract_text(path, mineru_config=config.get("mineru", {})):
                indexed_chunks = CTX.kb.index_text(
                    course_id=course_id,
                    file_id=file_node["id"],
                    file_name=file_node["name"],
                    text=page["text"],
                    page=page.get("page"),
                )
            indexed_files += 1
        return self.send_json({"ok": True, "indexed_files": indexed_files, "total_chunks": indexed_chunks})

    def chat(self, course_id: str, stream=False):
        body, uploads = self.read_maybe_multipart()
        question = body.get("question", "").strip()
        mode = body.get("mode", "answer")
        if not question and not uploads:
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
        course = CTX.find_course(course_id) or {"name": ""}
        if uploads:
            emit({"type": "status", "stage": "attachments", "detail": "正在读取附件…"})
        attachment_text, image_paths = self.index_chat_uploads(course_id, uploads)
        if (attachment_text or image_paths) and not question:
            question = "请阅读并总结我拖入的文件。"
        search_question = question
        if attachment_text:
            search_question = f"{question}\n\n拖入聊天框的文件内容：\n{attachment_text[:4000]}"
        if image_paths:
            image_names = "、".join(path.name for path in image_paths)
            search_question = f"{search_question}\n\n拖入聊天框的截图：{image_names}"
        CTX.store.add_message(course_id, "user", question)
        emit({"type": "status", "stage": "retrieval", "detail": "正在检索课程资料…"})
        result = CTX.kb.answer(course_id, search_question)
        config = CTX.config
        emit({"type": "status", "stage": "web", "detail": "正在判断是否需要联网…"})
        web_sources, web_status = self.retrieve_web_sources(
            question,
            result,
            config.get("web_search", {}),
            allow_web=not uploads,
        )
        local_sources = [
            {**source, "source_type": "local", "reference_label": f"L{index}"}
            for index, source in enumerate(result["citations"], start=1)
        ]
        labeled_web_sources = [
            {**source, "reference_label": f"W{index}"}
            for index, source in enumerate(web_sources, start=1)
        ]
        combined_result = dict(result)
        combined_result["citations"] = [*local_sources, *labeled_web_sources]
        if web_sources:
            combined_result["answer"] = append_web_fallback(result["answer"], labeled_web_sources)
        emit({"type": "status", "stage": "generation", "detail": "正在生成回答…"})
        if stream:
            prefix = answer_mode_prefix(mode)
            if prefix:
                emit({"type": "delta", "delta": prefix})
            generated_answer, llm_status = self.synthesize_answer_stream(
                search_question,
                combined_result,
                emit_delta=lambda delta: emit({"type": "delta", "delta": delta}),
                image_paths=image_paths,
                ai_config=config.get("ai", {}),
            )
            answer = prefix + generated_answer
        else:
            answer, llm_status = self.synthesize_answer(
                search_question,
                combined_result,
                image_paths=image_paths,
                ai_config=config.get("ai", {}),
            )
            answer = adapt_answer_by_mode(mode, answer)
        memory = CTX.store.update_memory_from_question(course_id, question)
        trace = build_agent_trace(
            course_name=course.get("name", ""),
            question=question,
            has_attachments=bool(uploads),
            citation_count=len(result["citations"]),
            memory_updated=True,
            llm_status=llm_status,
            web_status=web_status,
            web_source_count=len(web_sources),
        )
        CTX.store.add_message(course_id, "assistant", answer, combined_result["citations"], trace=trace)
        payload = {
            "answer": answer,
            "citations": combined_result["citations"],
            "memory": memory,
            "mode": mode,
            "trace": trace,
            "llm_status": llm_status,
            "web_search_status": web_status,
        }
        if stream:
            emit({"type": "done", "result": payload})
            self.end_stream()
            return None
        return self.send_json(payload)

    def retrieve_web_sources(self, question: str, result: dict, web_config=None, allow_web=True):
        if not allow_web or not should_search_web(question, result):
            return [], "skipped"
        client = create_web_search_client(web_config or {})
        if not client.enabled():
            return [], "disabled"
        try:
            sources = client.search(question)
        except WebSearchError:
            return [], "failed"
        return sources, "used" if sources else "empty"

    def create_study_artifact(self, course_id: str, artifact_type: str):
        course = CTX.find_course(course_id)
        if not course:
            return self.send_error_json("课程不存在", HTTPStatus.NOT_FOUND)
        if artifact_type == "summary":
            label = "课程摘要"
            result = CTX.kb.generate_summary(course_id)
        else:
            label = "练习题"
            result = CTX.kb.generate_quiz(course_id)
        artifact_path = save_study_artifact(Path(course["path"]), label, result["content"], result.get("citations", []))
        message = f"{label}已生成并保存到课程资料：{artifact_path.relative_to(Path(course['path']))}\n\n{result['content']}"
        CTX.store.add_message(course_id, "assistant", message, result.get("citations", []))
        return self.send_json(
            {
                "ok": True,
                "content": result["content"],
                "citations": result.get("citations", []),
                "artifact": {"name": artifact_path.name, "path": str(artifact_path)},
                "courses": CTX.courses(),
            }
        )

    def upload_course_files(self, course_id: str):
        course = CTX.find_course(course_id)
        if not course:
            return self.send_error_json("课程不存在", HTTPStatus.NOT_FOUND)
        _, uploads = self.read_maybe_multipart()
        if not uploads:
            return self.send_error_json("没有收到文件")
        saved = []
        for upload in uploads:
            try:
                path = save_course_upload(Path(course["path"]), upload["filename"], upload["content"])
            except ValueError as exc:
                return self.send_error_json(str(exc))
            saved.append({"name": path.name, "path": str(path)})
        return self.send_json({"ok": True, "saved": saved, "courses": CTX.courses()})

    def index_chat_uploads(self, course_id: str, uploads: list):
        if not uploads:
            return "", []
        config = CTX.config
        extracted_parts = []
        image_paths = []
        for upload in uploads:
            try:
                path = save_chat_upload(DATA_DIR, course_id, upload["filename"], upload["content"])
            except ValueError:
                continue
            if is_image_file(path):
                image_paths.append(path)
                extracted_parts.append(f"截图 {path.name} 已保存为聊天附件。")
                continue
            file_id = f"chat-{stable_id(str(path))}"
            page_texts = extract_text(path, mineru_config=config.get("mineru", {}))
            for page in page_texts:
                text = page.get("text", "")
                if not text.strip():
                    continue
                CTX.kb.index_text(
                    course_id=course_id,
                    file_id=file_id,
                    file_name=f"聊天附件/{path.name}",
                    text=text,
                    page=page.get("page"),
                )
                extracted_parts.append(f"文件 {path.name}：\n{text}")
        return "\n\n".join(extracted_parts), image_paths

    def synthesize_answer(self, question: str, result: dict, image_paths=None, ai_config=None):
        ai_config = ai_config if ai_config is not None else CTX.config.get("ai", {})
        image_paths = image_paths or []
        client = create_llm_client(ai_config)
        llm_configured = client.enabled()
        if image_paths:
            image_prompt = (
                "学生上传了课程截图或图片。请先理解图片内容，再结合课程资料回答。\n"
                "如果图片中文字看不清，直接说明看不清，不要编造。\n\n"
                f"学生问题：\n{question}\n\n"
                f"课程检索结果：\n{result.get('answer', '')}"
            )
            generated = client.generate_with_images(image_prompt, image_paths)
            if generated:
                return generated, "used"
            fallback = result["answer"]
            return (
                f"{fallback}\n\n"
                "已收到截图附件，但当前配置的大模型未成功读取图片内容。"
                "请确认 `data/config.json` 中配置的是支持视觉输入的 Kimi 模型，或把截图中的文字复制到聊天框。"
            ), "fallback" if llm_configured else "disabled"
        prompt = build_grounded_prompt(question, result["citations"], memory="")
        generated = client.generate(prompt)
        if generated:
            return generated, "used"
        return result["answer"], "fallback" if llm_configured else "disabled"

    def synthesize_answer_stream(
        self,
        question: str,
        result: dict,
        emit_delta,
        image_paths=None,
        ai_config=None,
    ):
        ai_config = ai_config if ai_config is not None else CTX.config.get("ai", {})
        image_paths = image_paths or []
        client = create_llm_client(ai_config)
        llm_configured = client.enabled()
        prompt = build_grounded_prompt(question, result["citations"], memory="")
        if image_paths:
            image_prompt = (
                "学生上传了课程截图或图片。请先理解图片内容，再结合课程资料回答。\n"
                "如果图片中文字看不清，直接说明看不清，不要编造。\n\n"
                f"学生问题：\n{question}\n\n"
                f"课程检索结果：\n{result.get('answer', '')}"
            )
            chunks = client.stream_with_images(image_prompt, image_paths)
            fallback_generate = lambda: client.generate_with_images(image_prompt, image_paths)
        else:
            chunks = client.stream(prompt)
            fallback_generate = lambda: client.generate(prompt)

        generated_parts = []
        for chunk in chunks or []:
            generated_parts.append(chunk)
            emit_delta(chunk)
        if generated_parts:
            return "".join(generated_parts), "used"

        generated = fallback_generate()
        if generated:
            emit_delta(generated)
            return generated, "used"
        fallback = result["answer"]
        if image_paths:
            fallback += (
                "\n\n已收到截图附件，但当前配置的大模型未成功读取图片内容。"
                "请确认模型支持视觉输入，或把截图中的文字复制到聊天框。"
            )
        emit_delta(fallback)
        return fallback, "fallback" if llm_configured else "disabled"

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
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        return json.loads(raw.decode("utf-8") or "{}")

    def read_maybe_multipart(self):
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            return self.read_body(), []
        form = cgi.FieldStorage(
            fp=self.rfile,
            headers=self.headers,
            environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type},
        )
        fields = {}
        uploads = []
        for key in form.keys():
            values = form[key]
            if not isinstance(values, list):
                values = [values]
            for item in values:
                if item.filename:
                    uploads.append({"filename": item.filename, "content": item.file.read()})
                else:
                    fields[key] = item.value
        return fields, uploads

    def send_json(self, payload, status=HTTPStatus.OK):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def begin_stream(self, stream_format="sse"):
        self.send_response(HTTPStatus.OK)
        content_type = (
            "text/event-stream; charset=utf-8"
            if stream_format == "sse"
            else "application/x-ndjson; charset=utf-8"
        )
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

    def send_stream_event(self, event, stream_format="sse"):
        payload = json.dumps(event, ensure_ascii=False)
        raw = (
            f"data: {payload}\n\n" if stream_format == "sse" else f"{payload}\n"
        ).encode("utf-8")
        frame = f"{len(raw):X}\r\n".encode("ascii") + raw + b"\r\n"
        try:
            self.wfile.write(frame)
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return False
        return True

    def end_stream(self):
        try:
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            return False
        return True

    def send_error_json(self, message, status=HTTPStatus.BAD_REQUEST):
        return self.send_json({"ok": False, "error": message}, status)


def iter_files(nodes):
    for node in nodes:
        if node["type"] == "file":
            yield node
        else:
            yield from iter_files(node.get("children", []))


def adapt_answer_by_mode(mode: str, answer: str) -> str:
    return answer_mode_prefix(mode) + answer


def answer_mode_prefix(mode: str) -> str:
    prefixes = {
        "socratic": "启发式提示：先不要急着看完整答案，可以根据资料中的关键词自己复述一遍。\n\n",
        "homework": "作业提示模式：以下只给思路和资料依据，不直接替你完成作业。\n\n",
        "review": "复习模式：建议把下面内容整理成概念、易错点和自测题。\n\n",
    }
    return prefixes.get(mode, "")


def append_web_fallback(answer: str, web_sources: list) -> str:
    lines = [answer, "", "网页搜索补充："]
    for index, source in enumerate(web_sources, start=1):
        snippet = source.get("quote", "").strip()
        lines.append(f"[W{index}] {source.get('file_name', '网页来源')}：{snippet}")
    return "\n".join(lines)


def save_study_artifact(course_path: Path, label: str, content: str, citations: list) -> Path:
    target_dir = course_path / "AI生成"
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = target_dir / f"{label}-{timestamp}.md"
    citation_lines = []
    for citation in citations:
        page = f" 第 {citation.get('page')} 页" if citation.get("page") else ""
        citation_lines.append(f"- {citation.get('file_name', '未知文件')}{page}，片段 {citation.get('chunk_index')}")
    text = f"# {label}\n\n{content.strip()}\n"
    if citation_lines:
        text += "\n## 来源\n\n" + "\n".join(citation_lines) + "\n"
    path.write_text(text, encoding="utf-8")
    return path


def should_index_course_file(course_path, file_path) -> bool:
    try:
        relative = Path(file_path).resolve().relative_to(Path(course_path).resolve())
    except ValueError:
        return False
    return "AI生成" not in relative.parts


def main():
    STATIC_DIR.mkdir(exist_ok=True)
    port = 8000
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Local Course Agent running at http://127.0.0.1:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
