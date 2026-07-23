from __future__ import annotations

from http import HTTPStatus

from local_course_agent.api.chat import (
    ChatFlow,
    ChatFlowError,
    index_chat_uploads as run_index_chat_uploads,
    retrieve_web_sources as run_retrieve_web_sources,
    synthesize_answer as run_synthesize_answer,
    synthesize_answer_stream as run_synthesize_answer_stream,
)
from local_course_agent.api.http import ClientDisconnected
from local_course_agent.llm.client import LLMRequestError


class ChatHttpMixin:
    def post_course_chat(self, course_id: str):
        accept = self.headers.get("Accept", "")
        stream_format = (
            "sse" if "text/event-stream" in accept
            else "ndjson" if "application/x-ndjson" in accept
            else None
        )
        try:
            return self.chat(course_id, stream=stream_format)
        except ClientDisconnected:
            return None

    def chat(self, course_id: str, stream=False):
        try:
            body, uploads = self.read_maybe_multipart()
        except ValueError as exc:
            return self.send_error_json(str(exc), HTTPStatus.REQUEST_ENTITY_TOO_LARGE)
        if getattr(self, "conversation_id", None):
            body = {**body, "conversation_id": self.conversation_id}
        if not str(body.get("question", "")).strip() and not uploads:
            return self.send_error_json("问题不能为空")
        emit = (lambda event: self.send_stream_event(event, stream)) if stream else (lambda _event: None)
        if stream:
            self.begin_stream(stream)
            emit(
                {
                    "type": "status",
                    "stage": "accepted",
                    "detail": "已收到问题，正在准备…",
                }
            )
        try:
            payload = ChatFlow(
                context=self.ctx,
                data_dir=self.data_dir,
                emit=emit,
                stream_format=stream,
                index_uploads=self.index_chat_uploads,
                retrieve_web=self.retrieve_web_sources,
                synthesize=self.synthesize_answer,
                synthesize_stream=self.synthesize_answer_stream,
            ).run(course_id, body, uploads)
        except (ChatFlowError, LLMRequestError) as exc:
            if stream:
                emit({"type": "error", "error": str(exc)})
                self.end_stream()
                return None
            return self.send_error_json(str(exc))
        if stream:
            emit({"type": "done", "result": payload})
            self.end_stream()
            return None
        return self.send_json(payload)

    def retrieve_web_sources(self, question: str, result: dict, web_config=None, allow_web=True, force_search=False):
        return run_retrieve_web_sources(question, result, web_config, allow_web, force_search)

    def index_chat_uploads(self, course_id: str, uploads: list):
        return run_index_chat_uploads(self.ctx, self.data_dir, course_id, uploads)

    def synthesize_answer(self, question: str, result: dict, image_paths=None, ai_config=None):
        return run_synthesize_answer(
            question,
            result,
            image_paths=image_paths,
            ai_config=ai_config if ai_config is not None else self.ctx.config.get("ai", {}),
        )

    def synthesize_answer_stream(
        self,
        question: str,
        result: dict,
        emit_delta,
        image_paths=None,
        ai_config=None,
    ):
        return run_synthesize_answer_stream(
            question,
            result,
            emit_delta=emit_delta,
            image_paths=image_paths,
            ai_config=ai_config if ai_config is not None else self.ctx.config.get("ai", {}),
        )
