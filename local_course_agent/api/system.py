from __future__ import annotations

import mimetypes
from http import HTTPStatus
from pathlib import Path
from typing import Any, Mapping

from local_course_agent.api.context import is_safe_material_root
from local_course_agent.api.course import ApiError
from local_course_agent.config import write_config
from local_course_agent.llm import create_llm_client
from local_course_agent.ops.config_status import build_config_status
from local_course_agent.web_search import create_web_search_client


def build_public_config_payload(config: Mapping[str, Any]) -> dict:
    ai_client = create_llm_client(config.get("ai", {}))
    mineru_config = config.get("mineru", {})
    web_client = create_web_search_client(config.get("web_search", {}))
    return {
        "root_folder": config.get("root_folder", ""),
        "ai_provider": config.get("ai", {}).get("provider", "openai_compatible"),
        "ai_configured": ai_client.enabled(),
        "mineru_auto": bool(mineru_config.get("auto", True)),
        "mineru_configured": bool(mineru_config.get("command") or mineru_config.get("token")),
        "web_search_configured": web_client.enabled(),
    }


def build_system_status_payload(data_dir: Path, config: Mapping[str, Any], courses) -> dict:
    return build_config_status(data_dir, config, courses)


def update_root_folder_payload(
    current_config: Mapping[str, Any],
    body: Mapping[str, Any],
    *,
    config_path: Path,
    project_root: Path,
    data_dir: Path,
) -> dict:
    root_folder = str(body.get("root_folder", current_config.get("root_folder", ""))).strip()
    if not root_folder:
        raise ApiError("请填写资料根目录")
    root = Path(root_folder).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise ApiError(f"资料根目录不存在: {root}")
    if not is_safe_material_root(root, project_root=project_root, data_dir=data_dir):
        raise ApiError("资料根目录不能设置为项目目录、数据目录或系统根目录")
    next_config = dict(current_config)
    next_config["root_folder"] = str(root)
    write_config(config_path, next_config)
    return {"ok": True, "config": {"root_folder": str(root)}}


def send_file_preview(handler, context, file_id: str) -> None:
    path = context.find_file(file_id)
    if not path:
        return handler.send_error_json("文件不存在", HTTPStatus.NOT_FOUND)
    ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    handler.send_response(HTTPStatus.OK)
    handler.send_header("Content-Type", ctype)
    handler.send_header("Content-Length", str(path.stat().st_size))
    handler.end_headers()
    with path.open("rb") as fh:
        handler.wfile.write(fh.read())
