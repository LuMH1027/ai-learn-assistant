from __future__ import annotations

from typing import Dict, Sequence

from local_course_agent.retrieval.conversation_context.references import extract_referenced_text
from local_course_agent.retrieval.conversation_context.schema import ContextualQuery
from local_course_agent.retrieval.conversation_context.signals import detect_follow_up_signals
from local_course_agent.retrieval.conversation_context.text import bounded_join, clean_text
from local_course_agent.retrieval.conversation_context.turns import compress_recent_turns, recent_conversation_turns


def build_contextual_retrieval_query(
    question: str,
    messages: Sequence[Dict],
    max_turns: int = 3,
    max_query_chars: int = 900,
) -> ContextualQuery:
    """Rewrite a follow-up question into a self-contained retrieval query.

    The function is deterministic and side-effect free. It only prepares text
    for retrieval; answer generation should still rely on retrieved evidence.
    """

    normalized_question = clean_text(question)
    signals = detect_follow_up_signals(normalized_question)
    turns = recent_conversation_turns(messages, max_turns=max_turns)
    referenced_text = extract_referenced_text(normalized_question, turns)

    if not signals or not turns:
        return ContextualQuery(
            original_query=normalized_question,
            retrieval_query=normalized_question,
            is_follow_up=False,
            signals=signals,
            context_turns_used=0,
        )

    context_text = referenced_text or compress_recent_turns(turns)
    retrieval_query = bounded_join(
        [
            "对话上下文",
            context_text,
            "当前追问",
            normalized_question,
        ],
        max_chars=max_query_chars,
    )

    return ContextualQuery(
        original_query=normalized_question,
        retrieval_query=retrieval_query,
        is_follow_up=True,
        signals=signals,
        context_turns_used=len(turns),
        referenced_text=referenced_text,
    )
