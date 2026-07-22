from __future__ import annotations

import json
from pathlib import Path


def course_index_stats(kb, course_id: str) -> dict:
    path_factory = getattr(kb, "_path", None)
    path = path_factory(course_id) if callable(path_factory) else None
    if not path:
        storage_dir = getattr(kb, "storage_dir", None)
        path = Path(storage_dir) / f"{course_id}.json" if storage_dir else None
    if not path or not Path(path).exists():
        return {"indexed_files": 0, "total_chunks": 0}
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"indexed_files": 0, "total_chunks": 0}
    if isinstance(payload, dict):
        chunks = payload.get("chunks", [])
        stats = {
            "schema_version": payload.get("schema_version"),
            "tokenizer_version": payload.get("tokenizer_version", ""),
        }
    elif isinstance(payload, list):
        chunks = payload
        stats = {"schema_version": None, "tokenizer_version": ""}
    else:
        chunks = []
        stats = {"schema_version": None, "tokenizer_version": ""}
    if not isinstance(chunks, list):
        chunks = []
    file_keys = {
        str(chunk.get("file_id") or chunk.get("file_name") or "")
        for chunk in chunks
        if isinstance(chunk, dict) and (chunk.get("file_id") or chunk.get("file_name"))
    }
    stats.update({"indexed_files": len(file_keys), "total_chunks": len(chunks)})
    return stats
