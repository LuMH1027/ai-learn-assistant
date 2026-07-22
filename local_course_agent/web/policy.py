from __future__ import annotations

import re
from typing import Mapping


FRESHNESS_RE = re.compile(
    r"最新|现在|目前|今天|今年|近期|最近|联网|网上|20\d{2}\s*年?|web\s*search|current|latest|today|recent",
    re.IGNORECASE,
)


def is_underspecified_query(question: str) -> bool:
    compact = re.sub(r"[^\w\u3400-\u9fff]+", "", question, flags=re.UNICODE)
    return not compact or bool(
        re.fullmatch(r"(?:\d+|[零〇一二三四五六七八九十百千万亿]+)", compact)
    )


def should_search_web(question: str, retrieval: Mapping) -> bool:
    if is_underspecified_query(question):
        return False
    if FRESHNESS_RE.search(question):
        return True
    return retrieval.get("retrieval_quality", "none") != "sufficient"
