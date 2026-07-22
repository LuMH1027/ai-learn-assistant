from __future__ import annotations

from local_course_agent.retrieval.conversation_context.references import extract_referenced_text
from local_course_agent.retrieval.conversation_context.rewrite import build_contextual_retrieval_query
from local_course_agent.retrieval.conversation_context.schema import ContextualQuery
from local_course_agent.retrieval.conversation_context.signals import detect_follow_up_signals
from local_course_agent.retrieval.conversation_context.turns import compress_recent_turns, recent_conversation_turns

__all__ = [
    "ContextualQuery",
    "build_contextual_retrieval_query",
    "detect_follow_up_signals",
    "recent_conversation_turns",
    "compress_recent_turns",
    "extract_referenced_text",
]
