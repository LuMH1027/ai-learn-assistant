from __future__ import annotations

import re
from typing import Dict, List, Sequence

from local_course_agent.retrieval.chunking import TOKEN_RE, tokenize


QUERY_STOP_TOKENS = {
    "什么",
    "怎么",
    "如何",
    "为什么",
    "哪些",
    "是否",
    "请问",
    "一下",
    "作用",
    "主要",
    "含义",
    "介绍",
    "说明",
}
QUERY_EXPANSIONS = {
    "地址转换": ["页表", "tlb", "虚拟地址", "物理地址"],
    "缺页": ["缺页中断", "页面置换", "调页"],
    "调度": ["进程", "线程", "cpu"],
    "后进先出": ["栈", "lifo"],
    "先进先出": ["队列", "fifo"],
    "映射": ["地址转换", "页表"],
    "缓存": ["tlb", "高速缓存"],
    "后备缓冲": ["tlb", "缓存"],
}


def normalize_query(query: str) -> str:
    normalized = query.lower()
    for stopword in sorted(QUERY_STOP_TOKENS, key=len, reverse=True):
        normalized = normalized.replace(stopword, " ")
    return normalized


def expand_query_tokens(query: str, tokens: Sequence[str]) -> List[str]:
    expanded = list(tokens)
    query_text = query.lower()
    for trigger, additions in QUERY_EXPANSIONS.items():
        trigger_tokens = tokenize(trigger)
        if trigger in query_text or any(token in tokens for token in trigger_tokens):
            expanded.extend(token for addition in additions for token in tokenize(addition))
    return expanded


def query_phrases(query: str) -> List[str]:
    phrases = []
    for phrase in TOKEN_RE.findall(query.lower()):
        if phrase in QUERY_STOP_TOKENS:
            continue
        if re.fullmatch(r"[\u4e00-\u9fff]+", phrase):
            cleaned = phrase
            for stopword in QUERY_STOP_TOKENS:
                cleaned = cleaned.replace(stopword, " ")
            phrases.extend(part for part in cleaned.split() if len(part) >= 2)
        elif len(phrase) >= 2:
            phrases.append(phrase)
    return phrases


def semantic_features(text: str) -> set[str]:
    features = set()
    for token in tokenize(text):
        if len(token) >= 2 and token not in QUERY_STOP_TOKENS:
            features.add(token)
    compact = re.sub(r"\s+", "", text.lower())
    features.update(compact[index : index + 4] for index in range(max(0, len(compact) - 3)))
    return features


def indexable_chunk_text(chunk: Dict) -> str:
    parts = [
        chunk.get("file_name", ""),
        chunk.get("file_path", ""),
        chunk.get("section_title", ""),
        chunk.get("text", ""),
    ]
    return "\n".join(part for part in parts if part)
