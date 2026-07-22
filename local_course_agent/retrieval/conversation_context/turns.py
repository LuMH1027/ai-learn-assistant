from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

from local_course_agent.retrieval.conversation_context.text import bounded_join, clean_text, compress_text


def recent_conversation_turns(messages: Sequence[Dict], max_turns: int = 3) -> Tuple[str, ...]:
    if max_turns <= 0:
        return ()

    turns: List[str] = []
    current_user = ""

    for message in messages:
        role = str(message.get("role", "")).lower()
        content = clean_text(str(message.get("content", "")))
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
    snippets = [compress_text(turn) for turn in turns if clean_text(turn)]
    return bounded_join(snippets, max_chars=max_chars)


def _format_turn(user_text: str, assistant_text: str) -> str:
    if assistant_text:
        return f"用户：{user_text}\n助手：{assistant_text}"
    return f"用户：{user_text}"
