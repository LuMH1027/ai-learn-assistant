from __future__ import annotations

from local_course_agent.web import (
    FRESHNESS_RE,
    MCP_PROTOCOL_VERSION,
    McpWebSearchClient,
    WebSearchError,
    classify_query_intent,
    create_web_search_client,
    is_relevant_source,
    is_underspecified_query,
    normalize_sources,
    should_search_web,
    source_quality,
    source_relevance,
)
from local_course_agent.web.normalization import (
    is_http_url as _is_http_url,
    parse_labeled_search_text as _parse_labeled_search_text,
    parse_sse_response as _parse_sse_response,
)

__all__ = [
    "FRESHNESS_RE",
    "MCP_PROTOCOL_VERSION",
    "McpWebSearchClient",
    "WebSearchError",
    "classify_query_intent",
    "create_web_search_client",
    "is_relevant_source",
    "is_underspecified_query",
    "normalize_sources",
    "should_search_web",
    "source_quality",
    "source_relevance",
]
