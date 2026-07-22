from __future__ import annotations

from typing import Dict, List, Sequence

from local_course_agent.retrieval.chunking import material_type, split_structured_text, tokenize


def append_text_chunks(
    chunks: List[Dict],
    course_id: str,
    file_id: str,
    file_name: str,
    text: str,
    page=None,
    file_path: str = "",
    next_index: int = 1,
) -> int:
    for structured_chunk in split_structured_text(text):
        text_chunk = structured_chunk["text"]
        section_title = structured_chunk.get("section_title", "")
        indexed_text = f"{section_title}\n{text_chunk}" if section_title else text_chunk
        chunks.append(
            {
                "id": f"{file_id}-{page or 'text'}-{next_index}",
                "course_id": course_id,
                "file_id": file_id,
                "file_name": file_name,
                "file_path": file_path,
                "section_title": section_title,
                "material_type": material_type(file_name, file_path),
                "page": page,
                "chunk_index": next_index,
                "text": text_chunk,
                "tokens": tokenize(indexed_text),
            }
        )
        next_index += 1
    return next_index


def build_document_chunks(course_id: str, documents: Sequence[Dict]) -> List[Dict]:
    chunks: List[Dict] = []
    next_index = 1
    for document in documents:
        for page in document.get("pages", []):
            next_index = append_text_chunks(
                chunks,
                course_id=course_id,
                file_id=document["file_id"],
                file_name=document["file_name"],
                text=page.get("text", ""),
                page=page.get("page"),
                file_path=document.get("path", ""),
                next_index=next_index,
            )
    return chunks
