from __future__ import annotations

import re
from typing import Mapping


FRESHNESS_RE = re.compile(
    r"最新|现在|目前|今天|今年|近期|最近|联网|网上|20\d{2}\s*年?|web\s*search|current|latest|today|recent",
    re.IGNORECASE,
)

COURSE_EXPLAIN_RE = re.compile(
    r"讲一下|解释|说明|总结|概括|复习|知识点|课程内容|这节课|这个课程|帮我学|怎么理解|what is|explain|summari[sz]e",
    re.IGNORECASE,
)
WEB_INTENT_RE = re.compile(
    r"联网|网上|搜索|查一下|资料外|补充资料|外部资料|竞品|官网|论文|新闻|current|latest|web\s*search|search",
    re.IGNORECASE,
)
LIGHT_CHAT_RE = re.compile(
    r"^(?:你好|您好|嗨|hi|hello|hey|早上好|晚上好|好|好的|可以|收到|明白|谢谢|谢了|ok|yes|no)[。！!？?\s]*$",
    re.IGNORECASE,
)


def is_underspecified_query(question: str) -> bool:
    compact = re.sub(r"[^\w\u3400-\u9fff]+", "", question, flags=re.UNICODE)
    return not compact or bool(
        re.fullmatch(r"(?:\d+|[零〇一二三四五六七八九十百千万亿]+)", compact)
    )


def classify_query_intent(question: str, retrieval: Mapping | None = None) -> str:
    retrieval = retrieval or {}
    if is_underspecified_query(question):
        return "clarification"
    if LIGHT_CHAT_RE.fullmatch(question.strip()):
        return "light_followup"
    if FRESHNESS_RE.search(question) or WEB_INTENT_RE.search(question):
        return "web_lookup"
    if COURSE_EXPLAIN_RE.search(question):
        return "course_explain"
    if retrieval.get("retrieval_quality", "none") == "none":
        return "general_question"
    return "course_question"


def should_search_web(question: str, retrieval: Mapping) -> bool:
    intent = classify_query_intent(question, retrieval)
    if intent in {"clarification", "light_followup", "course_explain", "course_question"}:
        return False
    if intent == "web_lookup":
        return True
    return retrieval.get("retrieval_quality", "none") == "none"
