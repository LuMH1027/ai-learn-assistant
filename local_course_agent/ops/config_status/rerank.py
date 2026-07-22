from __future__ import annotations

from typing import Dict, Mapping

from local_course_agent.config import resolve_siliconflow_api_key
from local_course_agent.ops.config_status.model import capability
from local_course_agent.retrieval.reranking import NoopReranker, create_reranker


def rerank_status(ai_config: Mapping) -> Dict:
    ai_config = dict(ai_config or {})
    configured_model = str(ai_config.get("rerank_model") or "").strip()
    configured_base_url = str(
        ai_config.get("rerank_base_url") or ai_config.get("base_url") or ""
    ).strip()
    configured_key = resolve_siliconflow_api_key(
        ai_config.get("rerank_api_key"), ai_config.get("api_key")
    )
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
