from __future__ import annotations

import re
from urllib.parse import urlparse


TOKEN_RE = re.compile(r"[A-Za-z0-9_]{2,}|[\u3400-\u9fff]{2,}")
STOP_TOKENS = {
    "一下",
    "什么",
    "怎么",
    "为什么",
    "这个",
    "那个",
    "课程",
    "内容",
    "总结",
    "解释",
    "说明",
    "帮我",
    "please",
    "about",
    "what",
    "with",
    "from",
    "search",
    "latest",
}


def source_quality(url: str, title: str = "", snippet: str = "") -> float:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    quality = 0.0
    if host.endswith(".edu") or ".edu." in host:
        quality += 2.0
    if host.endswith(".gov") or ".gov." in host:
        quality += 2.0
    if any(name in host for name in ("docs.", "developer.", "wikipedia.org", "python.org")):
        quality += 1.0
    if parsed.scheme == "https":
        quality += 0.25
    if len(snippet.strip()) >= 80:
        quality += 0.5
    if re.search(r"官方|文档|documentation|reference|specification", title, re.IGNORECASE):
        quality += 0.5
    return quality


def query_tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in TOKEN_RE.findall(text or "")
        if token.lower() not in STOP_TOKENS and len(token.strip()) >= 2
    }


def source_relevance(query: str, title: str = "", snippet: str = "") -> float:
    tokens = query_tokens(query)
    if not tokens:
        return 0.0
    haystack = f"{title}\n{snippet}".lower()
    matched = sum(1 for token in tokens if token in haystack)
    return matched / max(len(tokens), 1)


def is_relevant_source(query: str, title: str = "", snippet: str = "") -> bool:
    tokens = query_tokens(query)
    if not tokens:
        return True
    return source_relevance(query, title, snippet) >= min(0.34, 1 / max(len(tokens), 1))
