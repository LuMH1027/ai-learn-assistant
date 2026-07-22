from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Dict, List

from local_course_agent.retrieval.chunking import INDEX_TOKENIZER_VERSION


GENERATED_ARTIFACT_RE = re.compile(r"^(?:课程摘要|练习题)-\d{8}-\d{6}\.md$", re.IGNORECASE)
INDEX_SCHEMA_VERSION = 2


class KnowledgeChunkStore:
    """JSON-backed chunk persistence for one course index directory."""

    def __init__(self, storage_dir: Path):
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def path(self, course_id: str) -> Path:
        return self.storage_dir / f"{course_id}.json"

    def vector_path(self, course_id: str) -> Path:
        return self.storage_dir / f"{course_id}.vector.json"

    def load(self, course_id: str) -> List[Dict]:
        path = self.path(course_id)
        if not path.exists():
            return []
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload.get("chunks", [])
        return payload

    def save(self, course_id: str, chunks: List[Dict]) -> None:
        payload = {
            "schema_version": INDEX_SCHEMA_VERSION,
            "tokenizer_version": INDEX_TOKENIZER_VERSION,
            "chunks": chunks,
        }
        atomic_write_text(self.path(course_id), json.dumps(payload, ensure_ascii=False, indent=2))

    def material_chunks(self, course_id: str) -> List[Dict]:
        return [
            chunk
            for chunk in self.load(course_id)
            if not GENERATED_ARTIFACT_RE.fullmatch(chunk.get("file_name", ""))
        ]


def atomic_write_text(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)
