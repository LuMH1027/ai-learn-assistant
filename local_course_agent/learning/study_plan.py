from __future__ import annotations

from pathlib import Path

from local_course_agent.learning.files import iter_files, should_index_course_file

PLAN_FILE_LIMIT = 8


def build_default_study_plan(course: dict) -> list[dict]:
    files = []
    for file_node in iter_files(course.get("children", [])):
        path = Path(file_node["path"])
        if not should_index_course_file(course["path"], path):
            continue
        if path.suffix.lower() not in {".pdf", ".md", ".markdown", ".txt", ".docx"}:
            continue
        files.append(file_node)

    ranked = sorted(files, key=study_plan_file_rank)[:PLAN_FILE_LIMIT]
    if not ranked:
        return [
            {
                "title": f"整理《{course.get('name', '课程')}》资料目录",
                "kind": "read",
                "status": "todo",
                "estimated_minutes": 25,
            }
        ]

    items = []
    for file_node in ranked:
        title, kind, minutes = study_plan_item_from_file(file_node)
        items.append(
            {
                "title": title,
                "kind": kind,
                "status": "todo",
                "estimated_minutes": minutes,
                "source_file_id": file_node["id"],
                "source_file_name": file_node["name"],
            }
        )
    items.append(
        {
            "title": "完成一次错题与薄弱点复盘",
            "kind": "review",
            "status": "todo",
            "estimated_minutes": 30,
        }
    )
    return items


def study_plan_file_rank(file_node: dict) -> tuple[int, str]:
    name = str(file_node.get("name", "")).lower()
    priority = 2
    if any(keyword in name for keyword in ("教材", "chapter", "lecture", "课件", "讲义")):
        priority = 0
    elif any(keyword in name for keyword in ("习题", "练习", "quiz", "作业", "复习")):
        priority = 1
    return priority, name


def study_plan_item_from_file(file_node: dict) -> tuple[str, str, int]:
    name = str(file_node.get("name", "课程资料"))
    lower_name = name.lower()
    if any(keyword in lower_name for keyword in ("习题", "练习", "quiz", "作业")):
        return f"完成并订正 {name}", "practice", 35
    if any(keyword in lower_name for keyword in ("复习", "summary", "总结")):
        return f"复盘 {name}", "review", 25
    return f"阅读并提炼 {name}", "read", 30


def study_plan_stats(items: list[dict]) -> dict:
    total = len(items)
    completed = len([item for item in items if item.get("status") == "done"])
    doing = len([item for item in items if item.get("status") == "doing"])
    remaining_minutes = sum(
        int(item.get("estimated_minutes", 0) or 0)
        for item in items
        if item.get("status") != "done"
    )
    next_item = next((item for item in items if item.get("status") == "doing"), None)
    if next_item is None:
        next_item = next((item for item in items if item.get("status") == "todo"), None)
    return {
        "total": total,
        "completed": completed,
        "doing": doing,
        "remaining_minutes": remaining_minutes,
        "progress_percent": round((completed / total) * 100) if total else 0,
        "next_item_id": next_item.get("id") if next_item else None,
    }


def study_plan_payload(store, course_id: str, course: dict, plan_builder=build_default_study_plan) -> dict:
    items = store.ensure_study_plan(course_id, plan_builder(course))
    return {"items": items, "stats": study_plan_stats(items)}
