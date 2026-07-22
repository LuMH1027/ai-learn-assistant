from __future__ import annotations

from pathlib import Path

from local_course_agent.learning.files import iter_files, should_index_course_file
from local_course_agent.learning.indexing.progress import emit_progress, index_job_file_payload


def collect_indexable_files(course: dict) -> list[dict]:
    return [
        file_node
        for file_node in iter_files(course.get("children", []))
        if should_index_course_file(course["path"], Path(file_node["path"]))
    ]


def parser_quality_file_payload(file_node: dict, path: Path, quality: dict) -> dict:
    return {
        "file_id": file_node["id"],
        "file_name": file_node["name"],
        "path": str(path),
        "status": quality.get("status", "failed"),
        "warnings": quality.get("warnings", []),
        "score": quality.get("score", 0.0),
    }


def document_payload(file_node: dict, path: Path, pages: list[dict]) -> dict:
    return {
        "file_id": file_node["id"],
        "file_name": file_node["name"],
        "path": str(path),
        "pages": pages,
    }


def extract_index_documents(
    course: dict,
    mineru_config: dict | None,
    progress_callback,
    extract_text_fn,
    parser_quality_fn,
) -> tuple[list[dict], list[dict], dict[str, int]]:
    documents = []
    quality_files = []
    quality_counts = {"ok": 0, "warning": 0, "failed": 0}
    indexable_files = collect_indexable_files(course)

    emit_progress(
        progress_callback,
        total_files=len(indexable_files),
        processed_files=0,
        progress=0,
        current_file=None,
    )
    for file_node in indexable_files:
        path = Path(file_node["path"])
        current_file = index_job_file_payload(file_node)
        emit_progress(progress_callback, current_file=current_file)
        try:
            pages = extract_text_fn(path, mineru_config=mineru_config or {})
        except Exception as exc:
            emit_progress(
                progress_callback,
                error_file={**current_file, "error": str(exc)},
                current_file=current_file,
            )
            raise

        quality = parser_quality_fn(pages)
        status = quality.get("status", "failed")
        quality_counts[status] = quality_counts.get(status, 0) + 1
        quality_files.append(parser_quality_file_payload(file_node, path, quality))
        documents.append(document_payload(file_node, path, pages))

        indexed_files = len(documents)
        emit_progress(
            progress_callback,
            processed_files=indexed_files,
            progress=round((indexed_files / len(indexable_files)) * 100) if indexable_files else 100,
            current_file=current_file,
        )

    return documents, quality_files, quality_counts
