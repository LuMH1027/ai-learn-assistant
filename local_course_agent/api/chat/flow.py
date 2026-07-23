from __future__ import annotations

from pathlib import Path
from typing import Callable

from local_course_agent.agent_strategy import build_agent_trace
from local_course_agent.api.telemetry import (
    TelemetryRecorder,
    compact_telemetry_payload,
    record_chat_llm_result,
    record_chat_retrieval_result,
    record_citation_check_result,
    record_web_result,
)

from . import steps as chat_steps
from .errors import ChatFlowError
from .generation import ChatAnswerGenerator, adapt_answer_by_mode, decide_tool_use
from .llm_adapter import synthesize_answer, synthesize_answer_stream
from .uploads import index_chat_uploads
from .web import retrieve_web_sources


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
        decide_tools=None,
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
        self.decide_tools = decide_tools or decide_tool_use
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
        config = self.context.config
        self.emit({"type": "status", "stage": "thinking", "detail": "正在判断是否需要课程资料或联网…"})
        with telemetry.span("model-tool-decision", stage="llm", attributes={"course_id": course_id}):
            tool_decision = self.decide_tools(
                question,
                course_name=course.get("name", ""),
                previous_messages=previous_messages,
                has_attachments=bool(uploads),
                ai_config=config.get("ai", {}),
            )

        if tool_decision.needs_clarification:
            needs_clarification = True
            result = {
                "answer": "",
                "citations": [],
                "retrieval_quality": "skipped",
                "retrieval_trace": {"skipped": True, "decision": "clarify"},
            }
        elif tool_decision.direct_answer:
            return self._run_direct_reply(course_id, course, question, mode, telemetry, tool_decision)
        elif tool_decision.use_course_materials:
            self.emit({"type": "status", "stage": "retrieval", "detail": "正在检索课程资料…"})
            with telemetry.span(
                "course-retrieval",
                stage="retrieval",
                attributes={"course_id": course_id, "model_decided": True},
            ):
                result = self.context.kb.answer(course_id, retrieval.search_question)
            record_chat_retrieval_result(telemetry, result)
        else:
            result = {
                "answer": "",
                "citations": [],
                "retrieval_quality": "skipped",
                "retrieval_trace": {"skipped": True, "decision": "model_skipped_course_search"},
            }

        needs_clarification = tool_decision.needs_clarification
        if needs_clarification:
            self.emit({"type": "status", "stage": "clarification", "detail": "问题信息不足，正在请求补充…"})
            web_sources, web_status = [], "clarification"
        elif not tool_decision.use_web_search:
            web_sources, web_status = [], "skipped"
        else:
            self.emit({"type": "status", "stage": "web", "detail": "正在联网补充资料…"})
            with telemetry.span("web-search", stage="web", attributes={"allow_web": not uploads, "model_decided": True}):
                web_sources, web_status = self.retrieve_web(
                    question,
                    result,
                    config.get("web_search", {}),
                    allow_web=not uploads,
                    force_search=True,
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
        trace.insert(3, {"label": "判断", "status": "ok", "detail": tool_decision.reason or "模型自主决定可用能力"})
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

    def _run_direct_reply(
        self,
        course_id: str,
        course: dict,
        question: str,
        mode: str,
        telemetry: TelemetryRecorder,
        tool_decision,
    ) -> dict:
        answer = adapt_answer_by_mode(mode, tool_decision.direct_answer)
        self.answer_generator._emit_delta(answer)
        record_chat_llm_result(telemetry, llm_status=tool_decision.llm_status, fallback_reason="direct_answer")
        trace = build_agent_trace(
            course_name=course.get("name", ""),
            question=question,
            has_attachments=False,
            citation_count=0,
            memory_updated=False,
            llm_status=tool_decision.llm_status,
            web_status="skipped",
            web_source_count=0,
            retrieval_skipped=True,
        )
        trace.insert(2, {"label": "判断", "status": "ok", "detail": tool_decision.reason or "模型直接回答，未请求工具"})
        self.context.store.add_message(course_id, "assistant", answer, [], trace=trace)
        return {
            "answer": answer,
            "citations": [],
            "memory": self.context.store.get_memory(course_id),
            "mode": mode,
            "trace": trace,
            "retrieval_trace": {"skipped": True, "decision": "direct_answer"},
            "citation_check": {"status": "skipped", "unsupported_count": 0, "claims_checked": 0},
            "unsupported_claims": [],
            "llm_status": tool_decision.llm_status,
            "web_search_status": "skipped",
            "telemetry": compact_telemetry_payload(telemetry),
        }
