from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple


@dataclass(frozen=True)
class ContextualQuery:
    original_query: str
    retrieval_query: str
    is_follow_up: bool
    signals: Tuple[str, ...]
    context_turns_used: int
    referenced_text: str = ""
