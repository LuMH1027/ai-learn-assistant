from __future__ import annotations

from local_course_agent.learning.dashboard.utils import compact, strip_sort_key, time_key


def recent_activity(
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
                "title": compact(content) or "空消息",
                "created_at": str(message.get("created_at", "")),
                "sort_key": time_key(message.get("created_at")),
            }
        )
    for note in notes:
        activities.append(
            {
                "type": "note",
                "title": str(note.get("title") or "未命名笔记"),
                "created_at": str(note.get("created_at", "")),
                "sort_key": time_key(note.get("created_at")),
            }
        )
    for item in study_plan:
        timestamp = item.get("completed_at") or item.get("updated_at") or item.get("created_at")
        activities.append(
            {
                "type": f"plan:{item.get('status', 'todo')}",
                "title": str(item.get("title") or "未命名学习项"),
                "created_at": str(timestamp or ""),
                "sort_key": time_key(timestamp),
            }
        )
    activities.extend(file_activity(node, "generated_artifact") for node in generated_files)
    return [strip_sort_key(item) for item in sorted(activities, key=lambda item: item["sort_key"], reverse=True)[:limit]]


def file_activity(node: dict, activity_type: str) -> dict:
    timestamp = node.get("updated_at") or node.get("modified_at") or node.get("created_at") or ""
    return {
        "type": activity_type,
        "title": str(node.get("name") or "未命名文件"),
        "created_at": str(timestamp),
        "sort_key": time_key(timestamp),
    }
