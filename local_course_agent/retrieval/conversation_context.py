from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Tuple


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
QUESTION_REFERENCE_RE = re.compile(r"第\s*([一二三四五六七八九十\d]+)\s*[问题题小问步]")
SHORT_FOLLOW_UP_RE = re.compile(r"^(怎么做|为什么|啥意思|什么意思|展开|继续|然后呢|答案呢|复杂度呢|证明呢)[？?。！!]*$")
TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")
NUMBERED_ITEM_RE = re.compile(
    r"(?:^|[\n\r\s:：。；;？?！!])(?:第?\s*)?([一二三四五六七八九十\d]+)[.、)）]\s*(.*?)(?=(?:[\n\r\s:：。；;？?！!](?:第?\s*)?[一二三四五六七八九十\d]+[.、)）])|$)",
    re.DOTALL,
)


@dataclass(frozen=True)
class ContextualQuery:
    original_query: str
    retrieval_query: str
    is_follow_up: bool
    signals: Tuple[str, ...]
    context_turns_used: int
    referenced_text: str = ""


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

    normalized_question = _clean_text(question)
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
    retrieval_query = _bounded_join(
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


def detect_follow_up_signals(question: str) -> Tuple[str, ...]:
    text = _clean_text(question)
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


def recent_conversation_turns(messages: Sequence[Dict], max_turns: int = 3) -> Tuple[str, ...]:
    if max_turns <= 0:
        return ()

    turns: List[str] = []
    current_user = ""

    for message in messages:
        role = str(message.get("role", "")).lower()
        content = _clean_text(str(message.get("content", "")))
        if not content:
            continue
        if role == "user":
            if current_user:
                turns.append(_format_turn(current_user, ""))
            current_user = content
        elif role == "assistant" and current_user:
            turns.append(_format_turn(current_user, content))
            current_user = ""

    if current_user:
        turns.append(_format_turn(current_user, ""))

    return tuple(turns[-max_turns:])


def compress_recent_turns(turns: Sequence[str], max_chars: int = 650) -> str:
    snippets = [_compress_text(turn) for turn in turns if _clean_text(turn)]
    return _bounded_join(snippets, max_chars=max_chars)


def extract_referenced_text(question: str, turns: Sequence[str], max_chars: int = 420) -> str:
    reference_number = _question_reference_number(question)
    if reference_number is None:
        return ""

    for turn in reversed(turns):
        items = _numbered_items(turn)
        if reference_number in items:
            return _bounded_join([items[reference_number]], max_chars=max_chars)
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
        content = _clean_text(match.group(2))
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


def _format_turn(user_text: str, assistant_text: str) -> str:
    if assistant_text:
        return f"用户：{user_text}\n助手：{assistant_text}"
    return f"用户：{user_text}"


def _compress_text(text: str, max_chars: int = 260) -> str:
    text = _clean_text(text)
    if len(text) <= max_chars:
        return text

    tokens = TOKEN_RE.findall(text)
    keyword_prefix = " ".join(tokens[:18])
    suffix_budget = max_chars - len(keyword_prefix) - 4
    if keyword_prefix and suffix_budget > 30:
        return f"{keyword_prefix} ... {text[-suffix_budget:]}"
    return text[: max_chars - 1] + "…"


def _bounded_join(parts: Iterable[str], max_chars: int) -> str:
    output = ""
    for part in parts:
        part = _clean_text(part)
        if not part:
            continue
        candidate = part if not output else f"{output}\n{part}"
        if len(candidate) <= max_chars:
            output = candidate
            continue
        remaining = max_chars - len(output) - (1 if output else 0)
        if remaining <= 0:
            break
        clipped = part[: max(remaining - 1, 0)] + "…"
        output = clipped if not output else f"{output}\n{clipped}"
        break
    return output


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()
