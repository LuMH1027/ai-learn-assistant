from __future__ import annotations

from local_course_agent.ingestion.parser_quality import evaluate_parser_quality
from local_course_agent.learning.indexing.documents import extract_index_documents
from local_course_agent.learning.indexing.progress import emit_progress
from local_course_agent.parser import extract_text


def build_course_index(
    kb,
    course: dict,
    course_id: str,
    mineru_config=None,
    progress_callback=None,
    extract_text_fn=extract_text,
    parser_quality_fn=evaluate_parser_quality,
) -> dict:
    documents, quality_files, quality_counts = extract_index_documents(
        course,
        mineru_config,
        progress_callback,
        extract_text_fn,
        parser_quality_fn,
    )
    indexed_chunks = kb.rebuild_course(course_id, documents)
    indexed_files = len(documents)
    emit_progress(
        progress_callback,
        processed_files=indexed_files,
        progress=100,
        current_file=None,
    )
    return {
        "ok": True,
        "indexed_files": indexed_files,
        "total_chunks": indexed_chunks,
        "parser_quality": {
            "files": quality_files,
            "counts": quality_counts,
        },
    }
