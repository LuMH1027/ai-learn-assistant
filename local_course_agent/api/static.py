from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse

from local_course_agent.api.context import STATIC_DIR


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
