from __future__ import annotations

from typing import Dict


def summary_citation_from_chunk(chunk: Dict) -> Dict:
    page = chunk.get("page")
    location = f"第 {page} 页" if page else f"片段 {chunk.get('chunk_index', 0)}"
    section_title = str(chunk.get("section_title") or "")
    return {
        "file_id": chunk.get("file_id", ""),
        "file_name": chunk.get("file_name", "未知文件"),
        "file_path": chunk.get("file_path") or chunk.get("path", ""),
        "page": page,
        "chunk_index": chunk.get("chunk_index", 0),
        "location": location,
        "quote": chunk.get("context_text") or chunk.get("text", ""),
        "section_title": section_title,
        "material_type": chunk.get("material_type", ""),
    }
