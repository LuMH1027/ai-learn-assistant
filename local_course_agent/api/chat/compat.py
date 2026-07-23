from __future__ import annotations

import sys
from pathlib import Path
from typing import Iterable

from local_course_agent.llm.config import create_llm_client
from local_course_agent.web_search import (
    WebSearchError,
    create_web_search_client,
    is_underspecified_query,
    should_search_web,
)

from . import steps as chat_steps
from .llm_adapter import (
    synthesize_answer as _synthesize_answer,
    synthesize_answer_stream as _synthesize_answer_stream,
)
from .web import retrieve_web_sources as _retrieve_web_sources


def _public_attr(name: str):
    public_module = sys.modules.get("local_course_agent.api.chat")
    return getattr(public_module, name, globals()[name])


def build_search_question(query: str, attachment_text: str = "", image_paths: Iterable[Path] | None = None) -> str:
    return chat_steps.build_search_question(query, attachment_text, image_paths)


def contextual_query_step(contextual_query) -> dict:
    return chat_steps.contextual_query_step(contextual_query)


def append_web_fallback(answer: str, web_sources: list) -> str:
    return chat_steps.append_web_fallback(answer, web_sources)


def retrieve_web_sources(question: str, result: dict, web_config=None, allow_web=True, force_search=False):
    return _retrieve_web_sources(
        question,
        result,
        web_config=web_config,
        allow_web=allow_web,
        force_search=force_search,
        client_factory=_public_attr("create_web_search_client"),
    )


def synthesize_answer(question: str, result: dict, image_paths=None, ai_config=None, mode: str = "answer", previous_messages=None):
    return _synthesize_answer(
        question,
        result,
        image_paths=image_paths,
        ai_config=ai_config,
        mode=mode,
        previous_messages=previous_messages,
        llm_client_factory=_public_attr("create_llm_client"),
    )


def synthesize_answer_stream(
    question: str,
    result: dict,
    emit_delta,
    image_paths=None,
    ai_config=None,
    mode: str = "answer",
    previous_messages=None,
):
    return _synthesize_answer_stream(
        question,
        result,
        emit_delta=emit_delta,
        image_paths=image_paths,
        ai_config=ai_config,
        mode=mode,
        previous_messages=previous_messages,
        llm_client_factory=_public_attr("create_llm_client"),
    )


__all__ = [
    "WebSearchError",
    "append_web_fallback",
    "build_search_question",
    "contextual_query_step",
    "create_llm_client",
    "create_web_search_client",
    "is_underspecified_query",
    "retrieve_web_sources",
    "should_search_web",
    "synthesize_answer",
    "synthesize_answer_stream",
]
