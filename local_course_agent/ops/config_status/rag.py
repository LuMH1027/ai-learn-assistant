from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, Mapping, Optional

from local_course_agent.ops.config_status.model import capability


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
