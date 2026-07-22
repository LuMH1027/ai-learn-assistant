from __future__ import annotations

from typing import Dict, List, Mapping

from local_course_agent.ops.config_status.model import capability
from local_course_agent.web_search import create_web_search_client


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
