from __future__ import annotations

from typing import Dict, List, Mapping, Optional, Sequence


def capability(
    key: str,
    label: str,
    status: str,
    enabled: bool,
    detail: str,
    missing: Optional[Sequence[str]] = None,
    meta: Optional[Mapping] = None,
) -> Dict:
    payload = {
        "key": key,
        "label": label,
        "status": status,
        "enabled": bool(enabled),
        "detail": detail,
        "missing": list(missing or []),
    }
    if meta:
        payload.update(dict(meta))
    return payload


def overall_status(capabilities: List[Mapping]) -> str:
    statuses = {item.get("status") for item in capabilities}
    if "error" in statuses:
        return "error"
    if "warning" in statuses:
        return "warning"
    return "ok"
