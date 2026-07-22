from __future__ import annotations

from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler
import sys

from local_course_agent.api.context import (
    CONFIG_PATH,
    DATA_DIR,
    PROJECT_ROOT,
    STATIC_DIR,
    AppContext,
)
from local_course_agent.api.http import (
    begin_chunked_stream,
    error_payload,
    read_json_body,
    read_request_payload,
    send_json_response,
    write_stream_end,
    write_stream_event,
)
from local_course_agent.api.server.chat_adapter import ChatHttpMixin
from local_course_agent.api.server.routes import ServerRoutesMixin
from local_course_agent.api.static import resolve_static_path, static_cache_control
from local_course_agent.api.course import ApiError
from local_course_agent.uploads import MAX_TOTAL_UPLOAD_BYTES


_DEFAULT_CTX = AppContext()


def _runtime_attr(name: str, default):
    server_module = sys.modules.get("local_course_agent.server")
    return getattr(server_module, name, default) if server_module is not None else default


class Handler(ChatHttpMixin, ServerRoutesMixin, SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    @property
    def ctx(self):
        return _runtime_attr("CTX", _DEFAULT_CTX)

    @property
    def data_dir(self):
        return _runtime_attr("DATA_DIR", DATA_DIR)

    @property
    def config_path(self):
        return _runtime_attr("CONFIG_PATH", CONFIG_PATH)

    @property
    def project_root(self):
        return _runtime_attr("PROJECT_ROOT", PROJECT_ROOT)

    @property
    def static_dir(self):
        return _runtime_attr("STATIC_DIR", STATIC_DIR)

    def translate_path(self, path):
        resolved = resolve_static_path(path, self.static_dir)
        return str(resolved if resolved is not None else self.static_dir / "__invalid__")

    def end_headers(self):
        cache_control = static_cache_control(self.path)
        if cache_control:
            self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("X-Frame-Options", "DENY")
        super().end_headers()

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
