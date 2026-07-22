from __future__ import annotations

from typing import Dict, Mapping

from local_course_agent.config import resolve_siliconflow_api_key
from local_course_agent.llm.config import create_llm_client
from local_course_agent.ops.config_status.model import capability


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
