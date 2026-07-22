from __future__ import annotations


def emit_progress(progress_callback, **changes) -> None:
    if not progress_callback:
        return
    progress_callback(changes)


def index_job_file_payload(file_node: dict) -> dict:
    return {
        "file_id": file_node.get("id"),
        "file_name": file_node.get("name", ""),
        "path": str(file_node.get("path", "")),
    }
