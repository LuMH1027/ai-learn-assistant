from __future__ import annotations

import hashlib
import math
import re
import urllib.error
from typing import List, Sequence


DEFAULT_DIMENSIONS = 64
DEFAULT_EMBEDDING_BATCH_SIZE = 32
DEFAULT_EMBEDDING_MAX_RETRIES = 2
DEFAULT_EMBEDDING_RETRY_DELAY = 1.0


def model_fingerprint(provider: str, base_url: str, model: str) -> str:
    material = "\n".join([provider.strip(), base_url.rstrip("/"), model.strip()])
    digest = hashlib.sha256(material.encode("utf-8")).hexdigest()[:16]
    return f"sha256:{digest}"


def retryable_http_status(status: int) -> bool:
    return status in {408, 409, 425, 429} or 500 <= status <= 599


def http_error_detail(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        body = ""
    if not body:
        return ""
    return f": {sanitize_error_snippet(body)}"


def sanitize_error_snippet(text: str, limit: int = 300) -> str:
    compact = " ".join(text.split())
    compact = re.sub(r"sk-[A-Za-z0-9_\-]{8,}", "sk-***", compact)
    if len(compact) > limit:
        return compact[:limit] + "..."
    return compact


def unit_vector(vector: Sequence[float]) -> List[float]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        return [0.0 for _ in vector]
    return [value / norm for value in vector]


def tokens(text: str) -> List[str]:
    normalized = text.lower()
    found = re.findall(r"[a-z0-9]+|[\u4e00-\u9fff]", normalized)
    cjk_chars = [token for token in found if len(token) == 1 and "\u4e00" <= token <= "\u9fff"]
    cjk_bigrams = [a + b for a, b in zip(cjk_chars, cjk_chars[1:])]
    return found + cjk_bigrams


def _tokens(text: str) -> List[str]:
    return tokens(text)
