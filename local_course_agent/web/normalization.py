from __future__ import annotations

import hashlib
import json
import re
from typing import Dict, List, Optional
from urllib.parse import urlparse

from local_course_agent.web.quality import source_quality


def normalize_sources(tool_result: Dict, max_results: Optional[int] = None) -> List[Dict]:
    candidates = _collect_source_candidates(tool_result)
    sources = []
    seen_urls = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        url = str(candidate.get("url") or candidate.get("link") or candidate.get("uri") or "").strip()
        if not is_http_url(url) or url in seen_urls:
            continue
        seen_urls.add(url)
        title = str(candidate.get("title") or candidate.get("name") or urlparse(url).netloc).strip()
        snippet = str(
            candidate.get("content")
            or candidate.get("snippet")
            or candidate.get("description")
            or candidate.get("text")
            or ""
        ).strip()
        sources.append(
            {
                "source_type": "web",
                "file_id": f"web-{hashlib.sha1(url.encode('utf-8')).hexdigest()[:16]}",
                "file_name": title[:180],
                "url": url,
                "page": None,
                "chunk_index": 0,
                "score": float(candidate.get("score", 0) or 0),
                "source_quality": source_quality(url, title, snippet),
                "quote": snippet[:360],
            }
        )
    ranked = sorted(
        sources,
        key=lambda source: (source["source_quality"], source["score"], len(source["quote"])),
        reverse=True,
    )
    return ranked[:max_results] if max_results is not None else ranked


def parse_sse_response(body: str, request_id) -> Optional[Dict]:
    matched = None
    for block in re.split(r"\r?\n\r?\n", body):
        data = "\n".join(
            line[5:].lstrip() for line in block.splitlines() if line.startswith("data:")
        )
        if not data:
            continue
        try:
            message = json.loads(data)
        except json.JSONDecodeError:
            continue
        if message.get("id") == request_id:
            matched = message
    return matched


def parse_labeled_search_text(text: str) -> List[Dict]:
    results = []
    for block in re.split(r"\n\s*---\s*\n", text):
        title_match = re.search(r"^Title:\s*(.+)$", block, re.MULTILINE)
        url_match = re.search(r"^URL:\s*(https?://\S+)$", block, re.MULTILINE)
        if not title_match or not url_match:
            continue
        highlights = re.split(r"^Highlights:\s*$", block, maxsplit=1, flags=re.MULTILINE)
        snippet = highlights[1].strip() if len(highlights) == 2 else ""
        results.append(
            {
                "title": title_match.group(1).strip(),
                "url": url_match.group(1).strip(),
                "content": snippet,
            }
        )
    return results


def is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _collect_source_candidates(tool_result: Dict) -> List[Dict]:
    candidates = []
    structured = tool_result.get("structuredContent")
    if isinstance(structured, dict):
        for key in ("results", "items", "sources", "data"):
            if isinstance(structured.get(key), list):
                candidates.extend(structured[key])
        if not candidates and any(key in structured for key in ("url", "link", "uri")):
            candidates.append(structured)

    for item in tool_result.get("content", []):
        if not isinstance(item, dict):
            continue
        if item.get("type") == "resource_link":
            candidates.append(item)
        elif item.get("type") == "resource" and isinstance(item.get("resource"), dict):
            candidates.append(item["resource"])
        elif item.get("type") == "text":
            text = item.get("text", "")
            try:
                parsed = json.loads(text)
            except (TypeError, json.JSONDecodeError):
                candidates.extend(parse_labeled_search_text(str(text)))
                continue
            if isinstance(parsed, list):
                candidates.extend(parsed)
            elif isinstance(parsed, dict):
                nested = next(
                    (
                        parsed.get(key)
                        for key in ("results", "items", "sources", "data")
                        if isinstance(parsed.get(key), list)
                    ),
                    None,
                )
                candidates.extend(nested if nested is not None else [parsed])
    return candidates
