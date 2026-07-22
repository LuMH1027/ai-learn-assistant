from __future__ import annotations

from local_course_agent.learning.dashboard.utils import int_value, status_rank


def learning_progress(study_plan: list[dict]) -> dict:
    total = len(study_plan)
    done = sum(1 for item in study_plan if item.get("status") == "done")
    doing = sum(1 for item in study_plan if item.get("status") == "doing")
    todo = sum(1 for item in study_plan if item.get("status", "todo") == "todo")
    remaining_minutes = sum(int_value(item.get("estimated_minutes")) for item in study_plan if item.get("status") != "done")
    completed_minutes = sum(int_value(item.get("estimated_minutes")) for item in study_plan if item.get("status") == "done")
    next_item = next_plan_item(study_plan)
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


def review_queue(study_plan: list[dict]) -> list[dict]:
    candidates = []
    for item in study_plan:
        if item.get("status") == "done":
            continue
        if item.get("kind") == "review" or item.get("status") == "doing":
            candidates.append(plan_item_summary(item))
    if not candidates:
        candidates = [plan_item_summary(item) for item in study_plan if item.get("status") != "done"]
    return sorted(candidates, key=lambda item: (status_rank(item["status"]), item["id"]))[:5]


def next_plan_item(study_plan: list[dict]) -> dict | None:
    return next((item for item in study_plan if item.get("status") == "doing"), None) or next(
        (item for item in study_plan if item.get("status", "todo") == "todo"),
        None,
    )


def plan_item_summary(item: dict) -> dict:
    return {
        "id": int_value(item.get("id")),
        "title": str(item.get("title") or "未命名学习项"),
        "kind": str(item.get("kind") or "read"),
        "status": str(item.get("status") or "todo"),
        "estimated_minutes": int_value(item.get("estimated_minutes")),
        "source_file_name": str(item.get("source_file_name") or ""),
    }
