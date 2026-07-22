from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Dict, List, Optional

from local_course_agent.web.normalization import (
    is_http_url,
    normalize_sources,
    parse_sse_response,
)


MCP_PROTOCOL_VERSION = "2025-06-18"


class WebSearchError(RuntimeError):
    pass


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
        return bool(self.config.get("enabled") and is_http_url(self.url))

    def search(self, query: str) -> List[Dict]:
        if not self.enabled() or not query.strip():
            return []
        self._initialize()
        tool_name, request_id = self._resolve_tool_name()
        arguments = self._search_arguments(query)
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
        return normalize_sources(tool_result, max_results=self.max_results)

    def _initialize(self) -> None:
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

    def _resolve_tool_name(self) -> tuple[str, int]:
        tool_name = str(self.config.get("tool_name", "")).strip()
        if tool_name:
            return tool_name, 2

        listed = self._request(2, "tools/list", {})
        tools = listed.get("result", {}).get("tools", [])
        tool_name = next(
            (tool.get("name", "") for tool in tools if "search" in tool.get("name", "").lower()),
            "",
        )
        if not tool_name:
            raise WebSearchError("MCP 服务中未找到搜索工具")
        return tool_name, 3

    def _search_arguments(self, query: str) -> Dict:
        query_argument = str(self.config.get("query_argument", "query") or "query")
        arguments = {query_argument: query.strip()}
        max_results_argument = str(self.config.get("max_results_argument", "")).strip()
        if max_results_argument:
            arguments[max_results_argument] = self.max_results
        return arguments

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
        headers = self._headers(initialize=initialize)
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
            return parse_sse_response(body, payload.get("id"))
        try:
            return json.loads(body)
        except json.JSONDecodeError as exc:
            raise WebSearchError("MCP 返回了无效 JSON") from exc

    def _headers(self, initialize: bool = False) -> Dict[str, str]:
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
        return headers


def create_web_search_client(config: Dict) -> McpWebSearchClient:
    return McpWebSearchClient(config)
