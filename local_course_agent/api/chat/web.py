from __future__ import annotations

from local_course_agent.web_search import (
    WebSearchError,
    create_web_search_client,
    should_search_web,
)


def retrieve_web_sources(
    question: str,
    result: dict,
    web_config=None,
    allow_web=True,
    client_factory=create_web_search_client,
):
    if not allow_web or not should_search_web(question, result):
        return [], "skipped"
    client = client_factory(web_config or {})
    if not client.enabled():
        return [], "disabled"
    try:
        sources = client.search(question)
    except WebSearchError:
        return [], "failed"
    return sources, "used" if sources else "empty"
