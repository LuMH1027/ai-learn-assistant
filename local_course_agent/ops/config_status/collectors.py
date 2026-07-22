from __future__ import annotations

from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional

from local_course_agent.ops.config_status.ai import ai_generation_status
from local_course_agent.ops.config_status.filesystem import data_dir_status, material_root_status
from local_course_agent.ops.config_status.mineru import mineru_status
from local_course_agent.ops.config_status.rag import rag_index_status
from local_course_agent.ops.config_status.rerank import rerank_status
from local_course_agent.ops.config_status.runtime import backup_status, telemetry_status
from local_course_agent.ops.config_status.vector import vector_status
from local_course_agent.ops.config_status.web import web_search_status


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


__all__ = [
    "collect_config_capabilities",
    "ai_generation_status",
    "web_search_status",
    "mineru_status",
    "rag_index_status",
    "vector_status",
    "rerank_status",
    "telemetry_status",
    "backup_status",
]
