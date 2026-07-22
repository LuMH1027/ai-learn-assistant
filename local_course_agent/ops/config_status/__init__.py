from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional

from local_course_agent.config import normalize_config
from local_course_agent.ops.config_status.collectors import collect_config_capabilities
from local_course_agent.ops.config_status.model import overall_status


def build_config_status(
    data_dir: Path,
    config: Mapping,
    courses: Optional[Iterable[Mapping]] = None,
) -> Dict:
    normalized = normalize_config(dict(config or {}))
    root_folder = str(normalized.get("root_folder") or "")
    root_path = Path(root_folder).expanduser() if root_folder else None
    data_path = Path(data_dir)
    capabilities = collect_config_capabilities(
        data_path=data_path,
        root_path=root_path,
        ai_config=normalized.get("ai", {}),
        web_config=normalized.get("web_search", {}),
        mineru_config=normalized.get("mineru", {}),
        courses=courses,
    )

    return {
        "data_dir": str(data_path),
        "root_folder": root_folder,
        "overall": overall_status(capabilities),
        "capabilities": capabilities,
    }


__all__ = ["build_config_status"]
