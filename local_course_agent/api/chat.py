from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Callable, Iterable

from local_course_agent.agent_strategy import build_agent_trace
from local_course_agent.llm import build_grounded_prompt, create_llm_client
from local_course_agent.api import chat_steps
from local_course_agent.api.telemetry import (
    TelemetryRecorder,
    compact_telemetry_payload,
    record_chat_llm_result,
    record_chat_retrieval_result,
    record_citation_check_result,
    record_web_result,
)
from local_course_agent.parser import extract_text
from local_course_agent.scanner import is_image_file, stable_id
from local_course_agent.uploads import save_chat_upload
from local_course_agent.web_search import (
    WebSearchError,
    create_web_search_client,
    is_underspecified_query,
    should_search_web,
)


CLARIFICATION_ANSWER = "你的问题信息不足，请补充完整题目、知识点名称，或说明输入的编号对应哪一道题。为避免误导，本次没有联网搜索，也没有调用模型猜测。"


def emit_stream_text(text: str, emit, paced=False, delay=0.016) -> None:
    units = re.findall(r"[\u3400-\u9fff]|[A-Za-z0-9_]+|\s+|[^\s]", text) if paced else [text]
    for unit in units:
        emit({"type": "delta", "delta": unit})
        if paced and delay:
            time.sleep(delay)


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
        self.synthesize = synthesize or synthesize_answer
        self.synthesize_stream = synthesize_stream or synthesize_answer_stream

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
            answer, llm_status = self._generate_answer(
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

    def _generate_answer(
        self,
        *,
        mode: str,
        needs_clarification: bool,
        search_question: str,
        combined_result: dict,
        image_paths: list[Path],
        ai_config: dict,
    ) -> tuple[str, str]:
        if needs_clarification:
            answer = adapt_answer_by_mode(mode, CLARIFICATION_ANSWER)
            self._emit_delta(answer)
            return answer, "skipped"

        if self.stream_format:
            prefix = answer_mode_prefix(mode)
            if prefix:
                self._emit_delta(prefix)
            generated, llm_status = self.synthesize_stream(
                search_question,
                combined_result,
                emit_delta=self._emit_delta,
                image_paths=image_paths,
                ai_config=ai_config,
            )
            return prefix + generated, llm_status

        answer, llm_status = self.synthesize(
            search_question,
            combined_result,
            image_paths=image_paths,
            ai_config=ai_config,
        )
        return adapt_answer_by_mode(mode, answer), llm_status

    def _emit_delta(self, delta: str) -> None:
        emit_stream_text(delta, self.emit, paced=self.stream_format == "ndjson")


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
    image_paths = image_paths or []
    client = create_llm_client(ai_config or {})
    llm_configured = client.enabled()
    if image_paths:
        image_prompt = image_grounded_prompt(question, result)
        generated = client.generate_with_images(image_prompt, image_paths)
        if generated:
            return generated, "used"
        fallback = result["answer"]
        return (
            f"{fallback}\n\n"
            "已收到截图附件，但当前配置的大模型未成功读取图片内容。"
            "请确认 `data/config.json` 中配置的是支持视觉输入的 Kimi 模型，或把截图中的文字复制到聊天框。"
        ), "fallback" if llm_configured else "disabled"
    prompt = build_grounded_prompt(question, result["citations"], memory="")
    generated = client.generate(prompt)
    if generated:
        return generated, "used"
    return result["answer"], "fallback" if llm_configured else "disabled"


def synthesize_answer_stream(
    question: str,
    result: dict,
    emit_delta,
    image_paths=None,
    ai_config=None,
):
    image_paths = image_paths or []
    client = create_llm_client(ai_config or {})
    llm_configured = client.enabled()
    prompt = build_grounded_prompt(question, result["citations"], memory="")
    if image_paths:
        image_prompt = image_grounded_prompt(question, result)
        chunks = client.stream_with_images(image_prompt, image_paths)
        fallback_generate = lambda: client.generate_with_images(image_prompt, image_paths)
    else:
        chunks = client.stream(prompt)
        fallback_generate = lambda: client.generate(prompt)

    generated_parts = []
    for chunk in chunks or []:
        generated_parts.append(chunk)
        emit_delta(chunk)
    if generated_parts:
        return "".join(generated_parts), "used"

    generated = fallback_generate()
    if generated:
        emit_delta(generated)
        return generated, "used"
    fallback = result["answer"]
    if image_paths:
        fallback += (
            "\n\n已收到截图附件，但当前配置的大模型未成功读取图片内容。"
            "请确认模型支持视觉输入，或把截图中的文字复制到聊天框。"
        )
    emit_delta(fallback)
    return fallback, "fallback" if llm_configured else "disabled"


def image_grounded_prompt(question: str, result: dict) -> str:
    return (
        "学生上传了课程截图或图片。请先理解图片内容，再结合课程资料回答。\n"
        "如果图片中文字看不清，直接说明看不清，不要编造。\n\n"
        f"学生问题：\n{question}\n\n"
        f"课程检索结果：\n{result.get('answer', '')}"
    )


def adapt_answer_by_mode(mode: str, answer: str) -> str:
    return answer_mode_prefix(mode) + answer


def answer_mode_prefix(mode: str) -> str:
    prefixes = {
        "socratic": "启发式提示：先不要急着看完整答案，可以根据资料中的关键词自己复述一遍。\n\n",
        "homework": "作业提示模式：以下只给思路和资料依据，不直接替你完成作业。\n\n",
        "review": "复习模式：建议把下面内容整理成概念、易错点和自测题。\n\n",
    }
    return prefixes.get(mode, "")


def append_web_fallback(answer: str, web_sources: list) -> str:
    return chat_steps.append_web_fallback(answer, web_sources)
