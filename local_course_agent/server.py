from __future__ import annotations

from http.server import ThreadingHTTPServer

from local_course_agent.config import resolve_server_settings
from local_course_agent.api.chat import CLARIFICATION_ANSWER, emit_stream_text
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
from local_course_agent.api.course import course_index_stats
from local_course_agent.api.http import ClientDisconnected
from local_course_agent.api.router import parse_course_route
from local_course_agent.api.server.handler import Handler
from local_course_agent.api.static import (
    frontend_build_error,
    is_frontend_entry,
    resolve_static_path,
    static_cache_control,
)
from local_course_agent.learning.service import should_index_course_file


CTX = AppContext()


def main():
    STATIC_DIR.mkdir(exist_ok=True)
    host, port = resolve_server_settings(CTX.config)
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Local Course Agent running at http://{host}:{port}")
    server.serve_forever()


__all__ = [
    "CLARIFICATION_ANSWER",
    "CONFIG_PATH",
    "CTX",
    "ClientDisconnected",
    "DATA_DIR",
    "Handler",
    "PROJECT_ROOT",
    "STATIC_DIR",
    "course_index_stats",
    "emit_stream_text",
    "find_file_node",
    "frontend_build_error",
    "is_frontend_entry",
    "is_safe_material_root",
    "main",
    "parse_course_route",
    "read_json",
    "resolve_static_path",
    "should_index_course_file",
    "static_cache_control",
    "write_json",
]


if __name__ == "__main__":
    main()
