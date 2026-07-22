from __future__ import annotations

import re
from typing import Dict, Sequence

from local_course_agent.retrieval.conversation_context.text import bounded_join, clean_text

QUESTION_REFERENCE_RE = re.compile(r"第\s*([一二三四五六七八九十\d]+)\s*[问题题小问步]")
NUMBERED_ITEM_RE = re.compile(
    r"(?:^|[\n\r\s:：。；;？?！!])(?:第?\s*)?([一二三四五六七八九十\d]+)[.、)）]\s*(.*?)(?=(?:[\n\r\s:：。；;？?！!](?:第?\s*)?[一二三四五六七八九十\d]+[.、)）])|$)",
    re.DOTALL,
)


def extract_referenced_text(question: str, turns: Sequence[str], max_chars: int = 420) -> str:
    reference_number = _question_reference_number(question)
    if reference_number is None:
        return ""

    for turn in reversed(turns):
        items = _numbered_items(turn)
        if reference_number in items:
            return bounded_join([items[reference_number]], max_chars=max_chars)
    return ""


def _question_reference_number(question: str) -> int | None:
    match = QUESTION_REFERENCE_RE.search(question)
    if not match:
        return None
    return _parse_number(match.group(1))


def _numbered_items(text: str) -> Dict[int, str]:
    items: Dict[int, str] = {}
    for match in NUMBERED_ITEM_RE.finditer(text):
        number = _parse_number(match.group(1))
        content = clean_text(match.group(2))
        if number and content:
            items[number] = content
    return items


def _parse_number(raw: str) -> int | None:
    raw = raw.strip()
    if raw.isdigit():
        return int(raw)

    values = {
        "一": 1,
        "二": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
        "十": 10,
    }
    if raw in values:
        return values[raw]
    if raw.startswith("十") and len(raw) == 2:
        return 10 + values.get(raw[1:], 0)
    if raw.endswith("十") and len(raw) == 2:
        return values.get(raw[:1], 0) * 10
    if "十" in raw:
        left, right = raw.split("十", 1)
        return values.get(left, 1) * 10 + values.get(right, 0)
    return None
