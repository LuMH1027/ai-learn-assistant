from __future__ import annotations

from datetime import datetime
from typing import Dict


def normalize_study_plan_item(item: Dict, timestamp: str) -> Dict:
    title = str(item.get("title", "")).strip()[:120]
    if not title:
        title = "未命名学习项"
    kind = str(item.get("kind", "read"))
    if kind not in {"read", "review", "practice"}:
        kind = "read"
    status = str(item.get("status", "todo"))
    if status not in {"todo", "doing", "done"}:
        status = "todo"
    try:
        estimated_minutes = int(item.get("estimated_minutes", 25))
    except (TypeError, ValueError):
        estimated_minutes = 25
    estimated_minutes = min(max(estimated_minutes, 5), 240)
    return {
        "id": int(item.get("id", 0)),
        "title": title,
        "kind": kind,
        "status": status,
        "estimated_minutes": estimated_minutes,
        "source_file_id": str(item.get("source_file_id", "")),
        "source_file_name": str(item.get("source_file_name", "")),
        "created_at": str(item.get("created_at") or timestamp),
        "updated_at": str(item.get("updated_at") or timestamp),
        "completed_at": str(item.get("completed_at") or ""),
    }


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
