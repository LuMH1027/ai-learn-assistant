from __future__ import annotations

from pathlib import Path
from typing import Callable, Iterable

from local_course_agent.agent_strategy import build_agent_trace
from local_course_agent.api import chat_steps
from local_course_agent.api.chat_generation import (
    CLARIFICATION_ANSWER,
    ChatAnswerGenerator,
    adapt_answer_by_mode,
    answer_mode_prefix,
    emit_stream_text,
    image_grounded_prompt,
    synthesize_answer as _synthesize_answer,
    synthesize_answer_stream as _synthesize_answer_stream,
)
from local_course_agent.api.telemetry import (
    TelemetryRecorder,
    compact_telemetry_payload,
    record_chat_llm_result,
    record_chat_retrieval_result,
    record_citation_check_result,
    record_web_result,
)
from local_course_agent.llm import create_llm_client
from local_course_agent.parser import extract_text
from local_course_agent.scanner import is_image_file, stable_id
from local_course_agent.uploads import save_chat_upload
from local_course_agent.web_search import (
    WebSearchError,
    create_web_search_client,
    is_underspecified_query,
    should_search_web,
)


class ChatFlow:
    def __init__(
        self,
        *,
        context,
        data_dir: Path,
        emit: Callable[[dict], None],
        stream_format: str | None = None,
        index_uploads=None,
        retrieve_web=None,
        synthesize=None,
        synthesize_stream=None,
    ):
        self.context = context
        self.data_dir = Path(data_dir)
        self.emit = emit
        self.stream_format = stream_format
        self.index_uploads = index_uploads or (
            lambda course_id, uploads: index_chat_uploads(self.context, self.data_dir, course_id, uploads)
        )
        self.retrieve_web = retrieve_web or retrieve_web_sources
        self.answer_generator = ChatAnswerGenerator(
            emit=emit,
            stream_format=stream_format,
            synthesize=synthesize or synthesize_answer,
            synthesize_stream=synthesize_stream or synthesize_answer_stream,
        )

    def run(self, course_id: str, body: dict, uploads: list) -> dict:
        telemetry = TelemetryRecorder()
        question = str(body.get("question", "")).strip()
        mode = body.get("mode", "answer")
        if not question and not uploads:
            raise ChatFlowError("问题不能为空")

        course = self.context.find_course(course_id) or {"name": ""}
        if uploads:
            self.emit({"type": "status", "stage": "attachments", "detail": "正在读取附件…"})
        with telemetry.span("chat-upload-index", stage="indexing", attributes={"upload_count": len(uploads)}):
            attachment_text, image_paths = self.index_uploads(course_id, uploads)
        attachment = chat_steps.build_attachment_context(question, attachment_text, image_paths)
        if uploads:
            telemetry.event(
                "chat-upload-index-result",
                stage="indexing",
                attributes={
                    "upload_count": len(uploads),
                    "extracted_chars": len(attachment_text),
                    "image_count": len(image_paths),
                },
            )
        question = attachment.question

        previous_messages = self.context.store.list_messages(course_id)
        retrieval = chat_steps.build_retrieval_context(question, previous_messages, attachment)

        self.context.store.add_message(course_id, "user", question)
        self.emit({"type": "status", "stage": "retrieval", "detail": "正在检索课程资料…"})
        with telemetry.span("course-retrieval", stage="retrieval", attributes={"course_id": course_id}):
            result = self.context.kb.answer(course_id, retrieval.search_question)
        record_chat_retrieval_result(telemetry, result)
        config = self.context.config

        needs_clarification = not uploads and is_underspecified_query(question)
        if needs_clarification:
            self.emit({"type": "status", "stage": "clarification", "detail": "问题信息不足，正在请求补充…"})
            web_sources, web_status = [], "clarification"
        else:
            self.emit({"type": "status", "stage": "web", "detail": "正在判断是否需要联网…"})
            with telemetry.span("web-search", stage="web", attributes={"allow_web": not uploads}):
                web_sources, web_status = self.retrieve_web(
                    question,
                    result,
                    config.get("web_search", {}),
                    allow_web=not uploads,
                )
        record_web_result(telemetry, web_status, web_sources, allow_web=not uploads)

        sources = chat_steps.build_source_context(result, web_sources, needs_clarification)

        self.emit({"type": "status", "stage": "generation", "detail": "正在生成回答…"})
        with telemetry.span(
            "llm-answer",
            stage="llm",
            attributes={"mode": mode, "image_count": len(attachment.image_paths)},
        ):
            answer, llm_status = self.answer_generator.generate(
                mode=mode,
                needs_clarification=needs_clarification,
                search_question=retrieval.search_question,
                combined_result=sources.combined_result,
                image_paths=attachment.image_paths,
                ai_config=config.get("ai", {}),
            )
        record_chat_llm_result(
            telemetry,
            llm_status=llm_status,
            fallback_reason="clarification" if needs_clarification else None,
        )
        memory = (
            self.context.store.get_memory(course_id)
            if needs_clarification
            else self.context.store.update_memory_from_question(course_id, question)
        )

        with telemetry.span(
            "citation-check",
            stage="citation_check",
            attributes={"citation_count": len(sources.citations)},
        ):
            generation = chat_steps.postprocess_generation(answer, sources.citations)
        answer = generation.answer
        record_citation_check_result(telemetry, generation.citation_check)
        trace = build_agent_trace(
            course_name=course.get("name", ""),
            question=question,
            has_attachments=bool(uploads),
            citation_count=len(sources.local_sources),
            memory_updated=not needs_clarification,
            llm_status=llm_status,
            web_status=web_status,
            web_source_count=len(sources.web_sources),
        )
        trace.insert(2, chat_steps.contextual_query_step(retrieval.contextual_query))
        self.context.store.add_message(course_id, "assistant", answer, sources.citations, trace=trace)
        return {
            "answer": answer,
            "citations": sources.citations,
            "memory": memory,
            "mode": mode,
            "trace": trace,
            "retrieval_trace": chat_steps.retrieval_trace_with_context(result, retrieval),
            "citation_check": generation.citation_check,
            "unsupported_claims": generation.unsupported_claims,
            "llm_status": llm_status,
            "web_search_status": web_status,
            "telemetry": compact_telemetry_payload(telemetry),
        }


class ChatFlowError(ValueError):
    pass


def build_search_question(query: str, attachment_text: str = "", image_paths: Iterable[Path] | None = None) -> str:
    return chat_steps.build_search_question(query, attachment_text, image_paths)


def contextual_query_step(contextual_query) -> dict:
    return chat_steps.contextual_query_step(contextual_query)


def retrieve_web_sources(question: str, result: dict, web_config=None, allow_web=True):
    if not allow_web or not should_search_web(question, result):
        return [], "skipped"
    client = create_web_search_client(web_config or {})
    if not client.enabled():
        return [], "disabled"
    try:
        sources = client.search(question)
    except WebSearchError:
        return [], "failed"
    return sources, "used" if sources else "empty"


def index_chat_uploads(context, data_dir: Path, course_id: str, uploads: list):
    if not uploads:
        return "", []
    config = context.config
    extracted_parts = []
    image_paths = []
    for upload in uploads:
        try:
            path = save_chat_upload(Path(data_dir), course_id, upload["filename"], upload["content"])
        except ValueError as exc:
            raise ChatFlowError(str(exc)) from exc
        if is_image_file(path):
            image_paths.append(path)
            extracted_parts.append(f"截图 {path.name} 已保存为聊天附件。")
            continue
        file_id = f"chat-{stable_id(str(path))}"
        page_texts = extract_text(path, mineru_config=config.get("mineru", {}))
        for page in page_texts:
            text = page.get("text", "")
            if not text.strip():
                continue
            context.kb.index_text(
                course_id=course_id,
                file_id=file_id,
                file_name=f"聊天附件/{path.name}",
                text=text,
                page=page.get("page"),
            )
            extracted_parts.append(f"文件 {path.name}：\n{text}")
    return "\n\n".join(extracted_parts), image_paths


def synthesize_answer(question: str, result: dict, image_paths=None, ai_config=None):
    return _synthesize_answer(
        question,
        result,
        image_paths=image_paths,
        ai_config=ai_config,
        llm_client_factory=create_llm_client,
    )


def synthesize_answer_stream(
    question: str,
    result: dict,
    emit_delta,
    image_paths=None,
    ai_config=None,
):
    return _synthesize_answer_stream(
        question,
        result,
        emit_delta=emit_delta,
        image_paths=image_paths,
        ai_config=ai_config,
        llm_client_factory=create_llm_client,
    )


def append_web_fallback(answer: str, web_sources: list) -> str:
    return chat_steps.append_web_fallback(answer, web_sources)
