from __future__ import annotations

import re
from typing import List

from local_course_agent.retrieval.citations.labels import CITATION_RE


WORD_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")

CHINESE_STOP_CHARS = set("的一是在和与或及了为把对中上下面里个种这那其有就都而被并")
UNCERTAIN_MARKERS = (
    "可能",
    "也许",
    "大概",
    "或许",
    "不一定",
    "建议",
    "可以",
    "请",
    "复习时",
    "下一步",
    "如果",
    "当",
)
SUPPLEMENT_MARKERS = ("补充知识", "通用知识", "资料未覆盖", "未找到课程资料依据")


def split_sentences(answer: str) -> List[str]:
    sentences: List[str] = []
    for raw_line in answer.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^\s*[-*+]\s+", "", line)
        line = re.sub(r"^\s*\d+[.)、]\s+", "", line)
        if not line:
            continue
        sentences.extend(split_line(line))
    return sentences


def tokenize(text: str) -> List[str]:
    tokens: List[str] = []
    for match in WORD_RE.finditer(text.lower()):
        value = match.group(0)
        if re.fullmatch(r"[\u4e00-\u9fff]+", value):
            chars = [char for char in value if char not in CHINESE_STOP_CHARS]
            tokens.extend(chars)
            tokens.extend(value[index : index + 2] for index in range(len(value) - 1))
        elif len(value) > 1:
            tokens.append(value)
    return tokens


def split_line(line: str) -> List[str]:
    parts: List[str] = []
    start = 0
    index = 0
    while index < len(line):
        char = line[index]
        if char in "。！？!?；;":
            end = index + 1
            while True:
                cursor = end
                while cursor < len(line) and line[cursor].isspace():
                    cursor += 1
                label_match = CITATION_RE.match(line, cursor)
                if not label_match:
                    break
                end = label_match.end()
            while end < len(line) and line[end].isspace():
                end += 1
            parts.append(line[start:end].strip())
            start = end
            index = end
            continue
        index += 1
    tail = line[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def is_assertive_claim(text: str, token_count: int, min_claim_tokens: int) -> bool:
    if token_count < min_claim_tokens:
        return False
    stripped = text.strip()
    if not stripped or stripped.endswith(("?", "？")):
        return False
    if any(marker in stripped for marker in SUPPLEMENT_MARKERS):
        return False
    if any(stripped.startswith(marker) for marker in UNCERTAIN_MARKERS):
        return False
    return True
