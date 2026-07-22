from __future__ import annotations

import re
from typing import List, Tuple

from local_course_agent.retrieval.conversation_context.references import QUESTION_REFERENCE_RE
from local_course_agent.retrieval.conversation_context.text import clean_text

FOLLOW_UP_TERMS = (
    "这个",
    "这道",
    "这题",
    "这里",
    "上面",
    "前面",
    "刚才",
    "上一",
    "下面",
    "后面",
    "那个",
    "那道",
    "它",
    "其",
)
SHORT_FOLLOW_UP_RE = re.compile(r"^(怎么做|为什么|啥意思|什么意思|展开|继续|然后呢|答案呢|复杂度呢|证明呢)[？?。！!]*$")


def detect_follow_up_signals(question: str) -> Tuple[str, ...]:
    text = clean_text(question)
    if not text:
        return ()

    signals: List[str] = []
    for term in FOLLOW_UP_TERMS:
        if term in text:
            signals.append(term)

    reference = QUESTION_REFERENCE_RE.search(text)
    if reference:
        signals.append(f"第{reference.group(1)}问")

    if SHORT_FOLLOW_UP_RE.match(text):
        signals.append("short_follow_up")

    if len(text) <= 8 and text.endswith("呢"):
        signals.append("short_follow_up")

    return tuple(dict.fromkeys(signals))
