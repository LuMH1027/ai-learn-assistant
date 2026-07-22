from __future__ import annotations

from typing import Any, Mapping


def candidate_text(candidate: Mapping[str, Any]) -> str:
    section = str(candidate.get("section_title") or "").strip()
    file_name = str(candidate.get("file_name") or "").strip()
    text = str(candidate.get("context_text") or candidate.get("text") or "").strip()
    prefix = " ".join(part for part in (file_name, section) if part)
    return f"{prefix}\n{text}".strip()
