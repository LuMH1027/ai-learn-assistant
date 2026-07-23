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
from .generation import ChatAnswerGenerator, plan_agent_step
from .llm_adapter import synthesize_answer, synthesize_answer_stream
from .modes import normalize_study_mode
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
        plan_step=None,
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
        self.plan_step = plan_step or plan_agent_step
        self.answer_generator = ChatAnswerGenerator(
            emit=emit,
            stream_format=stream_format,
            synthesize=synthesize or synthesize_answer,
            synthesize_stream=synthesize_stream or synthesize_answer_stream,
        )

    def run(self, course_id: str, body: dict, uploads: list) -> dict:
        telemetry = TelemetryRecorder()
        question = str(body.get("question", "")).strip()
        conversation_id = str(body.get("conversation_id", "") or "").strip() or None
        mode = normalize_study_mode(body.get("mode", "answer"))
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

        previous_messages = self._list_messages(course_id, conversation_id)
        retrieval = chat_steps.build_retrieval_context(question, previous_messages, attachment)

        self._add_message(course_id, "user", question, conversation_id=conversation_id)
        config = self.context.config
        ai_config = self._ai_config_with_retry_status(config.get("ai", {}))
        result = {
            "answer": "",
            "citations": [],
            "retrieval_quality": "skipped",
            "retrieval_trace": {"skipped": True, "decision": "react_pending"},
        }
        web_sources, web_status = [], "skipped"
        observations = []
        final_status = "disabled"
        final_reason = ""
        needs_clarification = False
        clarification_answer = ""
        planner_fallback_answer = ""
        course_searched = False
        web_searched = False

        for turn in range(3):
            self.emit({"type": "status", "stage": "thinking", "detail": "正在思考下一步…"})
            with telemetry.span("react-step", stage="llm", attributes={"course_id": course_id, "turn": turn + 1}):
                step = self._plan_step(
                    question,
                    mode=mode,
                    course_name=course.get("name", ""),
                    previous_messages=previous_messages,
                    has_attachments=bool(uploads),
                    observations=observations,
                    ai_config=ai_config,
                )
            final_status = step.llm_status
            final_reason = step.reason
            self.emit({
                "type": "thought",
                "action": step.action,
                "detail": step.reason or react_action_label(step.action),
                "query": step.query[:120] if step.query else "",
            })

            if step.action == "final":
                planner_fallback_answer = step.answer
                break
            if step.action == "clarify":
                clarification_answer = step.answer
                needs_clarification = True
                final_status = "skipped"
                web_status = "clarification"
                break

            wants_course = step.action in {"course_search", "course_and_web_search"}
            wants_web = step.action in {"web_search", "course_and_web_search"}
            did_tool_work = False
            if wants_course and not course_searched:
                self.emit({"type": "status", "stage": "retrieval", "detail": "正在检索课程资料…"})
                course_query = (
                    retrieval.search_question
                    if retrieval.contextual_query.is_follow_up or attachment.has_content
                    else step.query or retrieval.search_question
                )
                with telemetry.span(
                    "course-retrieval",
                    stage="retrieval",
                    attributes={"course_id": course_id, "react_turn": turn + 1},
                ):
                    result = self.context.kb.answer(course_id, course_query)
                record_chat_retrieval_result(telemetry, result)
                course_searched = True
                did_tool_work = True
                observations.append({"action": "course_search", "summary": summarize_course_observation(result)})
            if wants_web and not web_searched:
                self.emit({"type": "status", "stage": "web", "detail": "正在联网补充资料…"})
                with telemetry.span("web-search", stage="web", attributes={"allow_web": not uploads, "react_turn": turn + 1}):
                    web_sources, web_status = self.retrieve_web(
                        step.query or question,
                        result,
                        config.get("web_search", {}),
                        allow_web=not uploads,
                        force_search=True,
                    )
                web_searched = True
                did_tool_work = True
                observations.append({"action": "web_search", "summary": summarize_web_observation(web_sources, web_status)})
            if did_tool_work:
                continue
            final_reason = final_reason or "已有 observation 足够，停止重复工具调用。"
            break
        record_web_result(telemetry, web_status, web_sources, allow_web=not uploads)

        sources = chat_steps.build_source_context(result, web_sources, needs_clarification)
        if needs_clarification:
            sources.combined_result["answer"] = clarification_answer
        elif planner_fallback_answer and not str(sources.combined_result.get("answer") or "").strip():
            sources.combined_result["answer"] = planner_fallback_answer

        answer, responder_status = self.answer_generator.generate(
            mode=mode,
            needs_clarification=needs_clarification,
            search_question=question,
            combined_result=sources.combined_result,
            image_paths=image_paths,
            ai_config=ai_config,
            previous_messages=previous_messages,
        )
        llm_status = responder_status if not needs_clarification else final_status
        record_chat_llm_result(telemetry, llm_status=llm_status, fallback_reason="clarification" if needs_clarification else None)
        memory = (
            self._get_memory(course_id, conversation_id)
            if needs_clarification
            else self._update_memory_from_question(course_id, question, conversation_id)
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
            retrieval_skipped=not course_searched,
        )
        trace.insert(2, chat_steps.contextual_query_step(retrieval.contextual_query))
        trace.insert(3, {"label": "ReAct", "status": "ok", "detail": final_reason or "模型完成 ReAct 推理"})
        self._add_message(course_id, "assistant", answer, sources.citations, trace=trace, conversation_id=conversation_id)
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

    def _ai_config_with_retry_status(self, ai_config: dict) -> dict:
        def retry_status(next_attempt: int, max_retries: int, exc: Exception) -> None:
            self.emit({
                "type": "status",
                "stage": "llm_retry",
                "detail": f"连接中断，正在重试 {next_attempt}/{max_retries}…",
            })

        return {**(ai_config or {}), "__retry_callback__": retry_status}

    def _plan_step(self, question: str, **kwargs):
        try:
            return self.plan_step(question, **kwargs)
        except TypeError:
            legacy_kwargs = {
                key: value
                for key, value in kwargs.items()
                if key in {"course_name", "previous_messages", "has_attachments", "observations", "ai_config"}
            }
            return self.plan_step(question, **legacy_kwargs)

    def _list_messages(self, course_id: str, conversation_id: str | None):
        if conversation_id is None:
            return self.context.store.list_messages(course_id)
        return self.context.store.list_messages(course_id, conversation_id)

    def _add_message(self, course_id: str, role: str, content: str, citations=None, trace=None, conversation_id: str | None = None):
        if conversation_id is None:
            return self.context.store.add_message(course_id, role, content, citations, trace)
        return self.context.store.add_message(course_id, role, content, citations, trace, conversation_id=conversation_id)

    def _get_memory(self, course_id: str, conversation_id: str | None):
        if conversation_id is None:
            return self.context.store.get_memory(course_id)
        return self.context.store.get_memory(course_id, conversation_id)

    def _update_memory_from_question(self, course_id: str, question: str, conversation_id: str | None):
        if conversation_id is None:
            return self.context.store.update_memory_from_question(course_id, question)
        return self.context.store.update_memory_from_question(course_id, question, conversation_id)


def summarize_course_observation(result: dict) -> str:
    citations = result.get("citations", [])[:3]
    lines = [str(result.get("answer") or "")[:900]]
    for index, citation in enumerate(citations, start=1):
        lines.append(f"[L{index}] {citation.get('file_name', '课程资料')}：{str(citation.get('quote', ''))[:280]}")
    return "\n".join(line for line in lines if line)


def summarize_web_observation(web_sources: list, status: str) -> str:
    if not web_sources:
        return f"联网状态：{status}，没有可引用网页。"
    lines = []
    for index, source in enumerate(web_sources[:3], start=1):
        lines.append(f"[W{index}] {source.get('file_name', '网页')}：{str(source.get('quote', ''))[:280]}")
    return "\n".join(lines)


def react_action_label(action: str) -> str:
    labels = {
        "final": "直接回答",
        "course_search": "检索课程资料",
        "web_search": "联网搜索",
        "course_and_web_search": "同时检索课程资料和联网资料",
        "clarify": "请求补充信息",
    }
    return labels.get(action, action)
