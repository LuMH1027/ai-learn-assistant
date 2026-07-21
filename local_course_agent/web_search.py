from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from typing import Dict, List, Optional
from urllib.parse import urlparse


MCP_PROTOCOL_VERSION = "2025-06-18"
FRESHNESS_RE = re.compile(
    r"最新|现在|目前|今天|今年|近期|最近|联网|网上|20\d{2}\s*年?|web\s*search|current|latest|today|recent",
    re.IGNORECASE,
)


class WebSearchError(RuntimeError):
    pass


def is_underspecified_query(question: str) -> bool:
    compact = re.sub(r"[^\w\u3400-\u9fff]+", "", question, flags=re.UNICODE)
    return not compact or bool(
        re.fullmatch(r"(?:\d+|[零〇一二三四五六七八九十百千万亿]+)", compact)
    )


def should_search_web(question: str, retrieval: Dict) -> bool:
    if is_underspecified_query(question):
        return False
    if FRESHNESS_RE.search(question):
        return True
    return retrieval.get("retrieval_quality", "none") != "sufficient"


class McpWebSearchClient:
    """Minimal MCP Streamable HTTP client for structured web-search tools."""

    def __init__(self, config: Dict):
        self.config = config or {}
        self.url = str(self.config.get("mcp_url", "")).strip()
        self.timeout = int(self.config.get("timeout", 20) or 20)
        self.max_results = max(1, min(int(self.config.get("max_results", 5) or 5), 10))
        self.session_id: Optional[str] = None
        self.protocol_version = MCP_PROTOCOL_VERSION

    def enabled(self) -> bool:
        return bool(self.config.get("enabled") and _is_http_url(self.url))

    def search(self, query: str) -> List[Dict]:
        if not self.enabled() or not query.strip():
            return []
        initialized = self._request(
            1,
            "initialize",
            {
                "protocolVersion": MCP_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "local-course-agent", "version": "1.0.0"},
            },
            initialize=True,
        )
        result = initialized.get("result", {})
        negotiated = result.get("protocolVersion", MCP_PROTOCOL_VERSION)
        if negotiated not in {"2025-06-18", "2025-03-26"}:
            raise WebSearchError(f"不支持的 MCP 协议版本: {negotiated}")
        if "tools" not in result.get("capabilities", {}):
            raise WebSearchError("MCP 服务未声明 tools 能力")
        self.protocol_version = negotiated
        self._notification("notifications/initialized")

        tool_name = str(self.config.get("tool_name", "")).strip()
        if not tool_name:
            listed = self._request(2, "tools/list", {})
            tools = listed.get("result", {}).get("tools", [])
            tool_name = next(
                (tool.get("name", "") for tool in tools if "search" in tool.get("name", "").lower()),
                "",
            )
            request_id = 3
        else:
            request_id = 2
        if not tool_name:
            raise WebSearchError("MCP 服务中未找到搜索工具")

        query_argument = str(self.config.get("query_argument", "query") or "query")
        arguments = {query_argument: query.strip()}
        max_results_argument = str(self.config.get("max_results_argument", "")).strip()
        if max_results_argument:
            arguments[max_results_argument] = self.max_results
        response = self._request(
            request_id,
            "tools/call",
            {"name": tool_name, "arguments": arguments},
        )
        tool_result = response.get("result", {})
        if tool_result.get("isError"):
            raise WebSearchError("MCP 搜索工具执行失败")
        return self.normalize_sources(tool_result)[: self.max_results]

    def normalize_sources(self, tool_result: Dict) -> List[Dict]:
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
                    candidates.extend(_parse_labeled_search_text(str(text)))
                    continue
                if isinstance(parsed, list):
                    candidates.extend(parsed)
                elif isinstance(parsed, dict):
                    nested = next(
                        (parsed.get(key) for key in ("results", "items", "sources", "data") if isinstance(parsed.get(key), list)),
                        None,
                    )
                    candidates.extend(nested if nested is not None else [parsed])

        sources = []
        seen_urls = set()
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            url = str(candidate.get("url") or candidate.get("link") or candidate.get("uri") or "").strip()
            if not _is_http_url(url) or url in seen_urls:
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
        return sorted(
            sources,
            key=lambda source: (source["source_quality"], source["score"], len(source["quote"])),
            reverse=True,
        )

    def _request(self, request_id: int, method: str, params: Dict, initialize: bool = False) -> Dict:
        payload = {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
        response = self._post(payload, initialize=initialize)
        if not isinstance(response, dict):
            raise WebSearchError(f"MCP {method} 未返回 JSON-RPC 响应")
        if response.get("error"):
            message = response["error"].get("message", "未知错误")
            raise WebSearchError(f"MCP {method} 失败: {message}")
        return response

    def _notification(self, method: str) -> None:
        self._post({"jsonrpc": "2.0", "method": method}, notification=True)

    def _post(self, payload: Dict, initialize: bool = False, notification: bool = False):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        if not initialize:
            headers["MCP-Protocol-Version"] = self.protocol_version
        if self.session_id:
            headers["Mcp-Session-Id"] = self.session_id
        api_key = str(self.config.get("api_key", "")).strip()
        if api_key:
            header = str(self.config.get("auth_header", "Authorization") or "Authorization")
            configured_scheme = self.config.get("auth_scheme", "Bearer")
            scheme = str(configured_scheme).strip() if configured_scheme is not None else "Bearer"
            headers[header] = f"{scheme} {api_key}".strip()
        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = response.read().decode("utf-8")
                if initialize:
                    self.session_id = response.headers.get("Mcp-Session-Id")
                if notification or not body:
                    return None
                content_type = response.headers.get("Content-Type", "")
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise WebSearchError(f"MCP 网络请求失败: {exc}") from exc
        if "text/event-stream" in content_type:
            return _parse_sse_response(body, payload.get("id"))
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise WebSearchError("MCP 返回了无效 JSON") from exc


def create_web_search_client(config: Dict) -> McpWebSearchClient:
    return McpWebSearchClient(config)


def _parse_sse_response(body: str, request_id) -> Optional[Dict]:
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


def _parse_labeled_search_text(text: str) -> List[Dict]:
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


def _is_http_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


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
