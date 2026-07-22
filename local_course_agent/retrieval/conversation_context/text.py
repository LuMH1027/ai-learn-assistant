from __future__ import annotations

import re
from typing import Iterable

TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def compress_text(text: str, max_chars: int = 260) -> str:
    text = clean_text(text)
    if len(text) <= max_chars:
        return text

    tokens = TOKEN_RE.findall(text)
    keyword_prefix = " ".join(tokens[:18])
    suffix_budget = max_chars - len(keyword_prefix) - 4
    if keyword_prefix and suffix_budget > 30:
        return f"{keyword_prefix} ... {text[-suffix_budget:]}"
    return text[: max_chars - 1] + "…"


def bounded_join(parts: Iterable[str], max_chars: int) -> str:
    output = ""
    for part in parts:
        part = clean_text(part)
        if not part:
            continue
        candidate = part if not output else f"{output}\n{part}"
        if len(candidate) <= max_chars:
            output = candidate
            continue
        remaining = max_chars - len(output) - (1 if output else 0)
        if remaining <= 0:
            break
        clipped = part[: max(remaining - 1, 0)] + "…"
        output = clipped if not output else f"{output}\n{clipped}"
        break
    return output
