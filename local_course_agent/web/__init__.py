from __future__ import annotations

from local_course_agent.web.mcp_client import (
    MCP_PROTOCOL_VERSION,
    McpWebSearchClient,
    WebSearchError,
    create_web_search_client,
)
from local_course_agent.web.normalization import (
    normalize_sources,
    parse_labeled_search_text,
    parse_sse_response,
)
from local_course_agent.web.policy import (
    FRESHNESS_RE,
    is_underspecified_query,
    should_search_web,
)
from local_course_agent.web.quality import source_quality

__all__ = [
    "FRESHNESS_RE",
    "MCP_PROTOCOL_VERSION",
    "McpWebSearchClient",
    "WebSearchError",
    "create_web_search_client",
    "is_underspecified_query",
    "normalize_sources",
    "parse_labeled_search_text",
    "parse_sse_response",
    "should_search_web",
    "source_quality",
]
