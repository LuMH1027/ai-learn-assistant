from __future__ import annotations

import re
from urllib.parse import urlparse


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
