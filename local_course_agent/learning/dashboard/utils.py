from __future__ import annotations

from datetime import datetime


def int_value(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def status_rank(status: str) -> int:
    return {"doing": 0, "todo": 1, "done": 2}.get(status, 1)


def time_key(value) -> str:
    text = str(value or "")
    if not text:
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y%m%d-%H%M%S"):
        try:
            return datetime.strptime(text[: len(fmt)], fmt).isoformat()
        except ValueError:
            continue
    return text


def is_due(value, timestamp: str | None = None) -> bool:
    target = time_key(value)
    if not target:
        return False
    now = time_key(timestamp) if timestamp else datetime.now().isoformat()
    return target <= now


def compact(text: str, limit: int = 72) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else f"{collapsed[:limit - 1]}..."


def strip_sort_key(item: dict | None) -> dict | None:
    if item is None:
        return None
    return {key: value for key, value in item.items() if key != "sort_key"}
