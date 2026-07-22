from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Protocol, Sequence

from local_course_agent.retrieval.citation_check import postprocess_answer_with_citation_check
from local_course_agent.retrieval.conversation_context import build_contextual_retrieval_query


class ContextualQueryLike(Protocol):
    is_follow_up: bool
    original_query: str
    retrieval_query: str
    signals: Sequence[str]
    context_turns_used: int
    referenced_text: str


@dataclass(frozen=True)
class AttachmentContext:
    question: str
    text: str
    image_paths: list[Path]

    @property
    def has_content(self) -> bool:
        return bool(self.text or self.image_paths)


@dataclass(frozen=True)
class RetrievalContext:
    contextual_query: ContextualQueryLike
    contextual_query_trace: dict
    search_question: str


@dataclass(frozen=True)
class SourceContext:
    local_sources: list[dict]
    web_sources: list[dict]
    combined_result: dict

    @property
    def citations(self) -> list[dict]:
        return self.combined_result["citations"]


@dataclass(frozen=True)
class GenerationContext:
    answer: str
    citation_check: dict
    unsupported_claims: list


def build_attachment_context(question: str, attachment_text: str, image_paths: Iterable[Path]) -> AttachmentContext:
    image_paths = list(image_paths or [])
    if (attachment_text or image_paths) and not question:
        question = "请阅读并总结我拖入的文件。"
    return AttachmentContext(question=question, text=attachment_text, image_paths=image_paths)


def build_retrieval_context(
    question: str,
    previous_messages: Sequence[Mapping],
    attachment: AttachmentContext,
) -> RetrievalContext:
    contextual_query = build_contextual_retrieval_query(question, previous_messages)
    contextual_query_trace = {
        "used": contextual_query.is_follow_up,
        "original_query": contextual_query.original_query,
        "retrieval_query": contextual_query.retrieval_query,
        "signals": list(contextual_query.signals),
        "context_turns_used": contextual_query.context_turns_used,
        "referenced_text": contextual_query.referenced_text,
    }
    return RetrievalContext(
        contextual_query=contextual_query,
        contextual_query_trace=contextual_query_trace,
        search_question=build_search_question(
            contextual_query.retrieval_query,
            attachment.text,
            attachment.image_paths,
        ),
    )


def build_search_question(query: str, attachment_text: str = "", image_paths: Iterable[Path] | None = None) -> str:
    search_question = query
    if attachment_text:
        search_question = f"{search_question}\n\n拖入聊天框的文件内容：\n{attachment_text[:4000]}"
    image_paths = list(image_paths or [])
    if image_paths:
        image_names = "、".join(path.name for path in image_paths)
        search_question = f"{search_question}\n\n拖入聊天框的截图：{image_names}"
    return search_question


def build_source_context(result: Mapping, web_sources: Sequence[Mapping], needs_clarification: bool) -> SourceContext:
    local_sources = label_local_sources([] if needs_clarification else result["citations"])
    labeled_web_sources = label_web_sources(web_sources)
    combined_result = dict(result)
    combined_result["citations"] = [*local_sources, *labeled_web_sources]
    if web_sources:
        combined_result["answer"] = append_web_fallback(result["answer"], labeled_web_sources)
    return SourceContext(
        local_sources=local_sources,
        web_sources=labeled_web_sources,
        combined_result=combined_result,
    )


def label_local_sources(sources: Sequence[Mapping]) -> list[dict]:
    return [
        {**source, "source_type": "local", "reference_label": f"L{index}"}
        for index, source in enumerate(sources, start=1)
    ]


def label_web_sources(sources: Sequence[Mapping]) -> list[dict]:
    return [{**source, "reference_label": f"W{index}"} for index, source in enumerate(sources, start=1)]


def postprocess_generation(answer: str, citations: Sequence[Mapping]) -> GenerationContext:
    payload = postprocess_answer_with_citation_check(answer, citations)
    return GenerationContext(
        answer=payload["answer"],
        citation_check=payload["citation_check"],
        unsupported_claims=payload["unsupported_claims"],
    )


def retrieval_trace_with_context(result: Mapping, retrieval: RetrievalContext) -> dict:
    retrieval_trace = dict(result.get("retrieval_trace", {}) or {})
    retrieval_trace["contextual_query"] = retrieval.contextual_query_trace
    return retrieval_trace


def contextual_query_step(contextual_query: ContextualQueryLike) -> dict:
    return {
        "label": "上下文",
        "status": "ok" if contextual_query.is_follow_up else "skip",
        "detail": (
            "检测到追问信号 "
            f"{'、'.join(contextual_query.signals)}，已使用最近 "
            f"{contextual_query.context_turns_used} 轮对话改写检索问题"
            if contextual_query.is_follow_up
            else "当前问题可独立检索，未改写检索问题"
        ),
    }


def append_web_fallback(answer: str, web_sources: Sequence[Mapping]) -> str:
    lines = [answer, "", "网页搜索补充："]
    for index, source in enumerate(web_sources, start=1):
        snippet = str(source.get("quote", "")).strip()
        lines.append(f"[W{index}] {source.get('file_name', '网页来源')}：{snippet}")
    return "\n".join(lines)
