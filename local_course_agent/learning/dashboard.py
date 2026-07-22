from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable

from local_course_agent.learning.mastery import normalize_state


GENERATED_FOLDER = "AI生成"
SUMMARY_KEYWORDS = ("摘要", "summary")
QUIZ_KEYWORDS = ("练习", "习题", "quiz", "自测")


def build_course_dashboard(
    course: dict,
    messages: list[dict] | None = None,
    notes: list[dict] | None = None,
    study_plan: list[dict] | None = None,
    mastery_state: dict | None = None,
    index_stats: dict | None = None,
    timestamp: str | None = None,
) -> dict:
    """Build a side-effect-free dashboard payload for one course."""

    messages = list(messages or [])
    notes = list(notes or [])
    study_plan = list(study_plan or [])
    index_stats = dict(index_stats or {})
    mastery = _mastery_summary(mastery_state, timestamp=timestamp)
    file_nodes = list(_iter_files(course.get("children", [])))
    generated_files = [node for node in file_nodes if _is_generated_file(course, node)]
    material_files = [node for node in file_nodes if node not in generated_files]

    progress = _learning_progress(study_plan)
    return {
        "course": {
            "id": course.get("id", ""),
            "name": course.get("name", ""),
            "path": course.get("path", ""),
        },
        "learning_progress": progress,
        "recent_activity": _recent_activity(messages, notes, study_plan, generated_files),
        "materials": _materials_stats(material_files, generated_files, index_stats),
        "review_queue": _review_queue(study_plan),
        "mastery": mastery,
        "generated_artifacts": _generated_artifacts(generated_files),
    }


def _learning_progress(study_plan: list[dict]) -> dict:
    total = len(study_plan)
    done = sum(1 for item in study_plan if item.get("status") == "done")
    doing = sum(1 for item in study_plan if item.get("status") == "doing")
    todo = sum(1 for item in study_plan if item.get("status", "todo") == "todo")
    remaining_minutes = sum(_int(item.get("estimated_minutes")) for item in study_plan if item.get("status") != "done")
    completed_minutes = sum(_int(item.get("estimated_minutes")) for item in study_plan if item.get("status") == "done")
    next_item = _next_plan_item(study_plan)
    return {
        "total": total,
        "done": done,
        "doing": doing,
        "todo": todo,
        "progress_percent": round((done / total) * 100) if total else 0,
        "remaining_minutes": remaining_minutes,
        "completed_minutes": completed_minutes,
        "next_item_id": next_item.get("id") if next_item else None,
        "next_item_title": next_item.get("title", "") if next_item else "",
    }


def _materials_stats(material_files: list[dict], generated_files: list[dict], index_stats: dict) -> dict:
    by_extension: dict[str, int] = {}
    total_bytes = 0
    for node in material_files:
        extension = str(node.get("extension") or Path(str(node.get("name", ""))).suffix).lower() or "unknown"
        by_extension[extension] = by_extension.get(extension, 0) + 1
        total_bytes += _int(node.get("size"))
    return {
        "file_count": len(material_files),
        "generated_file_count": len(generated_files),
        "total_bytes": total_bytes,
        "by_extension": dict(sorted(by_extension.items())),
        "indexed_files": _int(index_stats.get("indexed_files")),
        "indexed_chunks": _int(index_stats.get("total_chunks", index_stats.get("indexed_chunks"))),
        "schema_version": index_stats.get("schema_version"),
        "tokenizer_version": index_stats.get("tokenizer_version", ""),
    }


def _review_queue(study_plan: list[dict]) -> list[dict]:
    candidates = []
    for item in study_plan:
        if item.get("status") == "done":
            continue
        if item.get("kind") == "review" or item.get("status") == "doing":
            candidates.append(_plan_item_summary(item))
    if not candidates:
        candidates = [_plan_item_summary(item) for item in study_plan if item.get("status") != "done"]
    return sorted(candidates, key=lambda item: (_status_rank(item["status"]), item["id"]))[:5]


def _mastery_summary(state: dict | None, timestamp: str | None = None) -> dict:
    normalized = normalize_state(state or {}, timestamp=timestamp)
    points_by_id = {point["id"]: point for point in normalized["knowledge_points"]}
    records = list(normalized["mastery"].values())
    level_counts = {"weak": 0, "building": 0, "familiar": 0, "mastered": 0}
    for record in records:
        level = str(record.get("level") or "")
        if level in level_counts:
            level_counts[level] += 1

    open_mistakes = [item for item in normalized["mistakes"] if item.get("status") == "open"]
    due_reviews = [
        _mastery_item_summary(record, points_by_id, item_type="mastery_review")
        for record in records
        if _is_due(record.get("next_review_at"), timestamp)
    ]
    weakest_points = [
        _mastery_item_summary(record, points_by_id, item_type="weak_point")
        for record in sorted(records, key=lambda item: (_int(item.get("score")), str(item.get("updated_at"))))[:5]
    ]
    total_score = sum(_int(record.get("score")) for record in records)
    return {
        "knowledge_point_count": len(points_by_id),
        "tracked_count": len(records),
        "average_score": round(total_score / len(records)) if records else 0,
        "weak_count": level_counts["weak"],
        "building_count": level_counts["building"],
        "familiar_count": level_counts["familiar"],
        "mastered_count": level_counts["mastered"],
        "due_review_count": len(due_reviews),
        "open_mistake_count": len(open_mistakes),
        "weakest_points": weakest_points,
        "due_reviews": sorted(due_reviews, key=lambda item: (item["next_review_at"], item["score"]))[:5],
    }


def _mastery_item_summary(record: dict, points_by_id: dict[str, dict], item_type: str) -> dict:
    point_id = str(record.get("point_id") or "")
    point = points_by_id.get(point_id, {})
    return {
        "id": point_id,
        "type": item_type,
        "title": str(point.get("title") or point_id or "未命名知识点"),
        "score": _int(record.get("score")),
        "level": str(record.get("level") or ""),
        "attempts": _int(record.get("attempts")),
        "wrong_count": _int(record.get("wrong_count")),
        "next_review_at": str(record.get("next_review_at") or ""),
    }


def _generated_artifacts(generated_files: list[dict]) -> dict:
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
        activity = _file_activity(node, "generated_artifact")
        if latest is None or activity["sort_key"] > latest["sort_key"]:
            latest = activity
    return {
        "total": len(generated_files),
        "summaries": summary_count,
        "quizzes": quiz_count,
        "other": other_count,
        "latest": _strip_sort_key(latest) if latest else None,
    }


def _recent_activity(
    messages: list[dict],
    notes: list[dict],
    study_plan: list[dict],
    generated_files: list[dict],
    limit: int = 8,
) -> list[dict]:
    activities = []
    for message in messages:
        content = str(message.get("content", "")).strip()
        activities.append(
            {
                "type": f"message:{message.get('role', 'unknown')}",
                "title": _compact(content) or "空消息",
                "created_at": str(message.get("created_at", "")),
                "sort_key": _time_key(message.get("created_at")),
            }
        )
    for note in notes:
        activities.append(
            {
                "type": "note",
                "title": str(note.get("title") or "未命名笔记"),
                "created_at": str(note.get("created_at", "")),
                "sort_key": _time_key(note.get("created_at")),
            }
        )
    for item in study_plan:
        timestamp = item.get("completed_at") or item.get("updated_at") or item.get("created_at")
        activities.append(
            {
                "type": f"plan:{item.get('status', 'todo')}",
                "title": str(item.get("title") or "未命名学习项"),
                "created_at": str(timestamp or ""),
                "sort_key": _time_key(timestamp),
            }
        )
    activities.extend(_file_activity(node, "generated_artifact") for node in generated_files)
    return [_strip_sort_key(item) for item in sorted(activities, key=lambda item: item["sort_key"], reverse=True)[:limit]]


def _next_plan_item(study_plan: list[dict]) -> dict | None:
    return next((item for item in study_plan if item.get("status") == "doing"), None) or next(
        (item for item in study_plan if item.get("status", "todo") == "todo"),
        None,
    )


def _plan_item_summary(item: dict) -> dict:
    return {
        "id": _int(item.get("id")),
        "title": str(item.get("title") or "未命名学习项"),
        "kind": str(item.get("kind") or "read"),
        "status": str(item.get("status") or "todo"),
        "estimated_minutes": _int(item.get("estimated_minutes")),
        "source_file_name": str(item.get("source_file_name") or ""),
    }


def _file_activity(node: dict, activity_type: str) -> dict:
    timestamp = node.get("updated_at") or node.get("modified_at") or node.get("created_at") or ""
    return {
        "type": activity_type,
        "title": str(node.get("name") or "未命名文件"),
        "created_at": str(timestamp),
        "sort_key": _time_key(timestamp),
    }


def _iter_files(nodes: Iterable[dict]) -> Iterable[dict]:
    for node in nodes:
        if node.get("type") == "file":
            yield node
        elif node.get("type") == "folder":
            yield from _iter_files(node.get("children", []))


def _is_generated_file(course: dict, node: dict) -> bool:
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


def _status_rank(status: str) -> int:
    return {"doing": 0, "todo": 1, "done": 2}.get(status, 1)


def _time_key(value) -> str:
    text = str(value or "")
    if not text:
        return ""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y%m%d-%H%M%S"):
        try:
            return datetime.strptime(text[: len(fmt)], fmt).isoformat()
        except ValueError:
            continue
    return text


def _is_due(value, timestamp: str | None = None) -> bool:
    target = _time_key(value)
    if not target:
        return False
    now = _time_key(timestamp) if timestamp else datetime.now().isoformat()
    return target <= now


def _compact(text: str, limit: int = 72) -> str:
    collapsed = " ".join(text.split())
    return collapsed if len(collapsed) <= limit else f"{collapsed[:limit - 1]}..."


def _strip_sort_key(item: dict | None) -> dict | None:
    if item is None:
        return None
    return {key: value for key, value in item.items() if key != "sort_key"}


def _int(value) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
