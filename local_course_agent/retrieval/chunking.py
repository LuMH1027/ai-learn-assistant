from __future__ import annotations

import re
from typing import Dict, List


TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")
INDEX_TOKENIZER_VERSION = "zh_ngrams_v2"


def tokenize(text: str) -> List[str]:
    tokens: List[str] = []
    for raw in TOKEN_RE.findall(text):
        token = raw.lower()
        if not re.fullmatch(r"[\u4e00-\u9fff]+", token):
            tokens.append(token)
            continue
        if len(token) <= 8:
            tokens.append(token)
        if len(token) == 1:
            tokens.append(token)
            continue
        for width in (2, 3):
            tokens.extend(token[index : index + width] for index in range(len(token) - width + 1))
    return tokens


def split_text(text: str, chunk_size: int = 520, overlap: int = 80) -> List[str]:
    clean = re.sub(r"\s+", " ", text).strip()
    if not clean:
        return []
    chunks = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + chunk_size)
        chunks.append(clean[start:end])
        if end == len(clean):
            break
        start = max(end - overlap, start + 1)
    return chunks


def split_structured_text(text: str, chunk_size: int = 520, overlap: int = 80) -> List[Dict]:
    chunks = []
    for section in markdown_sections(text):
        for text_chunk in split_text(section["text"], chunk_size=chunk_size, overlap=overlap):
            chunks.append({"text": text_chunk, "section_title": section["title"]})
    return chunks


def markdown_sections(text: str) -> List[Dict]:
    sections = []
    current_title = ""
    current_lines = []
    for raw_line in text.splitlines():
        heading = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", raw_line)
        if heading:
            if current_lines:
                sections.append({"title": current_title, "text": "\n".join(current_lines).strip()})
            current_title = heading.group(2).strip()
            current_lines = [current_title]
            continue
        current_lines.append(raw_line)
    if current_lines:
        sections.append({"title": current_title, "text": "\n".join(current_lines).strip()})
    if not sections:
        return [{"title": "", "text": text}]
    return [section for section in sections if section["text"].strip()]


def material_type(file_name: str, file_path: str = "") -> str:
    text = f"{file_path}/{file_name}".lower()
    if any(keyword in text for keyword in ("习题", "练习", "quiz", "作业", "exercise")):
        return "practice"
    if any(keyword in text for keyword in ("课件", "slides", "ppt", "lecture")):
        return "slides"
    if any(keyword in text for keyword in ("教材", "book", "chapter", "讲义")):
        return "textbook"
    if any(keyword in text for keyword in ("笔记", "note")):
        return "notes"
    return "material"
