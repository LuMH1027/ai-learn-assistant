from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional

from local_course_agent.config import resolve_siliconflow_api_key
from local_course_agent.llm import create_llm_client
from local_course_agent.ops.backup import collect_backup_entries
from local_course_agent.ops.config_status.filesystem import data_dir_status, material_root_status
from local_course_agent.ops.config_status.model import capability
from local_course_agent.retrieval.rerankers import NoopReranker, create_reranker
from local_course_agent.retrieval.vector_index import create_embedding_model
from local_course_agent.web_search import create_web_search_client


def collect_config_capabilities(
    *,
    data_path: Path,
    root_path: Optional[Path],
    ai_config: Mapping,
    web_config: Mapping,
    mineru_config: Mapping,
    courses: Optional[Iterable[Mapping]] = None,
) -> List[Dict]:
    index_dir = data_path / "indexes"
    return [
        data_dir_status(data_path),
        material_root_status(root_path),
        ai_generation_status(ai_config),
        web_search_status(web_config),
        mineru_status(mineru_config),
        rag_index_status(index_dir, courses),
        vector_status(index_dir, ai_config),
        rerank_status(ai_config),
        telemetry_status(),
        backup_status(data_path),
    ]


def ai_generation_status(ai_config: Mapping) -> Dict:
    ai_config = dict(ai_config or {})
    api_key = resolve_siliconflow_api_key(ai_config.get("api_key"))
    missing = [
        key
        for key in ("base_url", "api_key", "model")
        if not (api_key if key == "api_key" else str(ai_config.get(key) or "").strip())
    ]
    enabled = create_llm_client(ai_config).enabled()
    provider = str(ai_config.get("provider") or "openai_compatible")
    return capability(
        "ai",
        "AI 生成",
        "ok" if enabled else "warning",
        enabled,
        f"{provider} 已配置" if enabled else "缺少大模型配置，回答和摘要会回退到本地检索结果。",
        missing,
        {
            "provider": provider,
            "model": str(ai_config.get("model") or "") if enabled else "",
        },
    )


def web_search_status(web_config: Mapping) -> Dict:
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
    return capability("web_search", "联网补充", status, enabled, detail, missing)


def mineru_status(mineru_config: Mapping) -> Dict:
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
    return capability("mineru", "文档解析", status, configured, detail, missing, {"auto": auto})


def rag_index_status(index_dir: Path, courses: Optional[Iterable[Mapping]]) -> Dict:
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
    return capability(
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


def vector_status(index_dir: Path, ai_config: Mapping) -> Dict:
    model = create_embedding_model(ai_config)
    vector_files = sorted(index_dir.glob("*.vector.json")) if index_dir.exists() else []
    real_provider = str(model.model_id).startswith("openai-compatible:")
    detail = (
        "已配置真实 embedding provider，可用于持久向量索引和混合检索。"
        if real_provider
        else "使用本地确定性 embedding，可离线运行；配置 SiliconFlow key 后可启用真实 embedding。"
    )
    if vector_files:
        detail = f"{detail} 检测到 {len(vector_files)} 个持久化向量索引。"
    return capability(
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
            "provider": "openai_compatible" if real_provider else "local",
        },
    )


def rerank_status(ai_config: Mapping) -> Dict:
    ai_config = dict(ai_config or {})
    configured_model = str(ai_config.get("rerank_model") or "").strip()
    configured_base_url = str(ai_config.get("rerank_base_url") or ai_config.get("base_url") or "").strip()
    configured_key = resolve_siliconflow_api_key(ai_config.get("rerank_api_key"), ai_config.get("api_key"))
    any_configured = any((configured_model, configured_base_url, configured_key))
    missing = []
    if any_configured and not configured_model:
        missing.append("rerank_model")
    if any_configured and not configured_base_url:
        missing.append("rerank_base_url_or_base_url")
    if any_configured and not configured_key:
        missing.append("rerank_api_key_or_api_key")

    reranker = create_reranker(ai_config)
    enabled = not isinstance(reranker, NoopReranker)
    if enabled:
        status = "ok"
        detail = "已配置外部 rerank provider，可用于 cross-encoder 候选重排。"
    elif any_configured:
        status = "warning"
        detail = "rerank 配置不完整，将回退到本地重排。"
    else:
        status = "skip"
        detail = "未配置外部 rerank，将使用本地重排。"
    return capability(
        "rerank",
        "候选重排",
        status,
        enabled,
        detail,
        missing,
        {
            "model": getattr(reranker, "model_id", "local-rerank"),
            "top_n": int(ai_config.get("rerank_top_n") or 12),
        },
    )


def telemetry_status() -> Dict:
    return capability(
        "telemetry",
        "遥测诊断",
        "ok",
        True,
        "内存遥测记录器可用，用于索引、检索和 LLM 诊断。",
        [],
        {"mode": "in_memory"},
    )


def backup_status(data_dir: Path) -> Dict:
    try:
        entries = collect_backup_entries(data_dir)
    except OSError:
        return capability("backup", "备份恢复", "warning", False, "无法读取可备份数据。")
    return capability(
        "backup",
        "备份恢复",
        "ok",
        True,
        f"可备份 {len(entries)} 个数据文件。",
        [],
        {"backup_file_count": len(entries)},
    )
