from __future__ import annotations

from typing import Dict, Mapping

from local_course_agent.ops.config_status.model import capability


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
