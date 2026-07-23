from __future__ import annotations

from local_course_agent.llm.config import create_llm_client

from .generation import (
    synthesize_answer as _synthesize_answer,
    synthesize_answer_stream as _synthesize_answer_stream,
)


def synthesize_answer(
    question: str,
    result: dict,
    image_paths=None,
    ai_config=None,
    mode: str = "answer",
    previous_messages=None,
    llm_client_factory=create_llm_client,
):
    return _synthesize_answer(
        question,
        result,
        image_paths=image_paths,
        ai_config=ai_config,
        mode=mode,
        previous_messages=previous_messages,
        llm_client_factory=llm_client_factory,
    )


def synthesize_answer_stream(
    question: str,
    result: dict,
    emit_delta,
    image_paths=None,
    ai_config=None,
    mode: str = "answer",
    previous_messages=None,
    llm_client_factory=create_llm_client,
):
    return _synthesize_answer_stream(
        question,
        result,
        emit_delta=emit_delta,
        image_paths=image_paths,
        ai_config=ai_config,
        mode=mode,
        previous_messages=previous_messages,
        llm_client_factory=llm_client_factory,
    )
