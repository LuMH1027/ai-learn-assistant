from __future__ import annotations

from pathlib import Path
from typing import Iterable

from local_course_agent.learning.dashboard_activity import file_activity
from local_course_agent.learning.dashboard_utils import int_value, strip_sort_key


GENERATED_FOLDER = "AI生成"
SUMMARY_KEYWORDS = ("摘要", "summary")
QUIZ_KEYWORDS = ("练习", "习题", "quiz", "自测")


def split_course_files(course: dict) -> tuple[list[dict], list[dict]]:
    file_nodes = list(iter_files(course.get("children", [])))
    generated_files = [node for node in file_nodes if is_generated_file(course, node)]
    material_files = [node for node in file_nodes if node not in generated_files]
    return material_files, generated_files


def materials_stats(material_files: list[dict], generated_files: list[dict], index_stats: dict) -> dict:
    by_extension: dict[str, int] = {}
    total_bytes = 0
    for node in material_files:
        extension = str(node.get("extension") or Path(str(node.get("name", ""))).suffix).lower() or "unknown"
        by_extension[extension] = by_extension.get(extension, 0) + 1
        total_bytes += int_value(node.get("size"))
    return {
        "file_count": len(material_files),
        "generated_file_count": len(generated_files),
        "total_bytes": total_bytes,
        "by_extension": dict(sorted(by_extension.items())),
        "indexed_files": int_value(index_stats.get("indexed_files")),
        "indexed_chunks": int_value(index_stats.get("total_chunks", index_stats.get("indexed_chunks"))),
        "schema_version": index_stats.get("schema_version"),
        "tokenizer_version": index_stats.get("tokenizer_version", ""),
    }


def generated_artifacts(generated_files: list[dict]) -> dict:
    summary_count = 0
    quiz_count = 0
    other_count = 0
    latest = None
    for node in generated_files:
        name = str(node.get("name", ""))
        lower_name = name.lower()
        if any(keyword in lower_name for keyword in SUMMARY_KEYWORDS):
            summary_count += 1
        elif any(keyword in lower_name for keyword in QUIZ_KEYWORDS):
            quiz_count += 1
        else:
            other_count += 1
        activity = file_activity(node, "generated_artifact")
        if latest is None or activity["sort_key"] > latest["sort_key"]:
            latest = activity
    return {
        "total": len(generated_files),
        "summaries": summary_count,
        "quizzes": quiz_count,
        "other": other_count,
        "latest": strip_sort_key(latest) if latest else None,
    }


def iter_files(nodes: Iterable[dict]) -> Iterable[dict]:
    for node in nodes:
        if node.get("type") == "file":
            yield node
        elif node.get("type") == "folder":
            yield from iter_files(node.get("children", []))


def is_generated_file(course: dict, node: dict) -> bool:
    path = str(node.get("path") or "")
    if GENERATED_FOLDER in Path(path).parts:
        return True
    course_path = str(course.get("path") or "")
    if course_path and path:
        try:
            return GENERATED_FOLDER in Path(path).resolve().relative_to(Path(course_path).resolve()).parts
        except (OSError, ValueError):
            pass
    return str(node.get("parent") or "") == GENERATED_FOLDER
