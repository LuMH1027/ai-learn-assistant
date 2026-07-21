from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional

from local_course_agent.backup import collect_backup_entries
from local_course_agent.config import normalize_config
from local_course_agent.llm import create_llm_client
from local_course_agent.vector_index import FakeEmbeddingModel
from local_course_agent.web_search import create_web_search_client


def build_config_status(
    data_dir: Path,
    config: Mapping,
    courses: Optional[Iterable[Mapping]] = None,
) -> Dict:
    normalized = normalize_config(dict(config or {}))
    root_folder = str(normalized.get("root_folder") or "")
    root_path = Path(root_folder).expanduser() if root_folder else None
    data_path = Path(data_dir)
    index_dir = data_path / "indexes"

    capabilities = [
        _data_dir_status(data_path),
        _root_status(root_path),
        _ai_status(normalized.get("ai", {})),
        _web_search_status(normalized.get("web_search", {})),
        _mineru_status(normalized.get("mineru", {})),
        _rag_index_status(index_dir, courses),
        _vector_status(index_dir),
        _telemetry_status(),
        _backup_status(data_path),
    ]
    overall = _overall_status(capabilities)

    return {
        "data_dir": str(data_path),
        "root_folder": root_folder,
        "overall": overall,
        "capabilities": capabilities,
    }


def _data_dir_status(data_dir: Path) -> Dict:
    exists = data_dir.exists()
    writable = _is_writable(data_dir)
    if exists and writable:
        return _capability("data_dir", "数据目录", "ok", True, str(data_dir))
    if exists:
        return _capability("data_dir", "数据目录", "warning", False, "数据目录存在，但当前不可写。")
    return _capability("data_dir", "数据目录", "warning", False, "数据目录尚未创建，首次写入时会尝试创建。")


def _root_status(root: Optional[Path]) -> Dict:
    if root is None:
        return _capability("material_root", "资料根目录", "warning", False, "尚未设置资料根目录。", ["root_folder"])
    expanded = root.expanduser()
    if expanded.exists() and expanded.is_dir():
        return _capability("material_root", "资料根目录", "ok", True, str(expanded))
    return _capability("material_root", "资料根目录", "error", False, f"资料根目录不存在：{expanded}")


def _ai_status(ai_config: Mapping) -> Dict:
    ai_config = dict(ai_config or {})
    missing = [
        key
        for key in ("base_url", "api_key", "model")
        if not str(ai_config.get(key) or "").strip()
    ]
    enabled = create_llm_client(ai_config).enabled()
    provider = str(ai_config.get("provider") or "openai_compatible")
    return _capability(
        "ai",
        "AI 生成",
        "ok" if enabled else "warning",
        enabled,
        f"{provider} 已配置" if enabled else "缺少大模型配置，回答和摘要会回退到本地检索结果。",
        missing,
        {"provider": provider},
    )


def _web_search_status(web_config: Mapping) -> Dict:
    web_config = dict(web_config or {})
    enabled = create_web_search_client(web_config).enabled()
    configured_enabled = bool(web_config.get("enabled"))
    missing: List[str] = []
    if configured_enabled and not str(web_config.get("mcp_url") or "").strip():
        missing.append("mcp_url")
    if configured_enabled and not str(web_config.get("tool_name") or "").strip():
        missing.append("tool_name")
    if enabled:
        status = "ok"
        detail = "联网补充已启用。"
    elif configured_enabled:
        status = "warning"
        detail = "联网补充已打开，但配置不完整。"
    else:
        status = "skip"
        detail = "联网补充未启用。"
    return _capability("web_search", "联网补充", status, enabled, detail, missing)


def _mineru_status(mineru_config: Mapping) -> Dict:
    mineru_config = dict(mineru_config or {})
    configured = bool(mineru_config.get("command") or mineru_config.get("token"))
    auto = bool(mineru_config.get("auto", True))
    if configured:
        detail = "高质量解析已配置。"
        status = "ok"
    elif auto:
        detail = "未配置 MinerU，将使用内置解析回退。"
        status = "warning"
    else:
        detail = "MinerU 未启用，将只使用内置解析。"
        status = "skip"
    missing = [] if configured else ["command_or_token"]
    return _capability("mineru", "文档解析", status, configured, detail, missing, {"auto": auto})


def _rag_index_status(index_dir: Path, courses: Optional[Iterable[Mapping]]) -> Dict:
    files = sorted(index_dir.glob("*.json")) if index_dir.exists() else []
    chunks = 0
    schema_versions = set()
    for path in files:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            continue
        if isinstance(payload, dict):
            raw_chunks = payload.get("chunks", [])
            if isinstance(payload.get("schema_version"), int):
                schema_versions.add(payload["schema_version"])
        elif isinstance(payload, list):
            raw_chunks = payload
        else:
            raw_chunks = []
        if isinstance(raw_chunks, list):
            chunks += len(raw_chunks)
    course_count = len(list(courses or []))
    if chunks > 0:
        status = "ok"
        detail = f"已有 {len(files)} 个课程索引、{chunks} 个资料片段。"
    elif course_count > 0:
        status = "warning"
        detail = "已识别课程，但还没有可用索引。"
    else:
        status = "warning"
        detail = "还没有课程索引。"
    return _capability(
        "rag_index",
        "RAG 索引",
        status,
        chunks > 0,
        detail,
        [],
        {
            "index_files": len(files),
            "total_chunks": chunks,
            "schema_versions": sorted(schema_versions),
        },
    )


def _vector_status(index_dir: Path) -> Dict:
    model = FakeEmbeddingModel()
    vector_files = sorted(index_dir.glob("*.vector.json")) if index_dir.exists() else []
    detail = "本地向量能力可用，可用于混合检索；当前未检测到持久化向量索引。"
    if vector_files:
        detail = f"检测到 {len(vector_files)} 个持久化向量索引。"
    return _capability(
        "vector",
        "向量检索",
        "ok",
        True,
        detail,
        [],
        {
            "model": model.model_id,
            "dimensions": model.dimensions,
            "index_files": len(vector_files),
        },
    )


def _telemetry_status() -> Dict:
    return _capability(
        "telemetry",
        "遥测诊断",
        "ok",
        True,
        "内存遥测记录器可用，用于索引、检索和 LLM 诊断。",
        [],
        {"mode": "in_memory"},
    )


def _backup_status(data_dir: Path) -> Dict:
    try:
        entries = collect_backup_entries(data_dir)
    except OSError:
        return _capability("backup", "备份恢复", "warning", False, "无法读取可备份数据。")
    return _capability(
        "backup",
        "备份恢复",
        "ok",
        True,
        f"可备份 {len(entries)} 个数据文件。",
        [],
        {"backup_file_count": len(entries)},
    )


def _capability(
    key: str,
    label: str,
    status: str,
    enabled: bool,
    detail: str,
    missing: Optional[List[str]] = None,
    meta: Optional[Dict] = None,
) -> Dict:
    payload = {
        "key": key,
        "label": label,
        "status": status,
        "enabled": bool(enabled),
        "detail": detail,
        "missing": list(missing or []),
    }
    if meta:
        payload.update(meta)
    return payload


def _overall_status(capabilities: List[Mapping]) -> str:
    statuses = {item.get("status") for item in capabilities}
    if "error" in statuses:
        return "error"
    if "warning" in statuses:
        return "warning"
    return "ok"


def _is_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".healthcheck"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True
    except OSError:
        return False
