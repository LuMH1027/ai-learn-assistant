from __future__ import annotations

from local_course_agent.learning.dashboard.utils import int_value, is_due
from local_course_agent.learning.mastery import normalize_state


def mastery_summary(state: dict | None, timestamp: str | None = None) -> dict:
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
        mastery_item_summary(record, points_by_id, item_type="mastery_review")
        for record in records
        if is_due(record.get("next_review_at"), timestamp)
    ]
    weakest_points = [
        mastery_item_summary(record, points_by_id, item_type="weak_point")
        for record in sorted(records, key=lambda item: (int_value(item.get("score")), str(item.get("updated_at"))))[:5]
    ]
    total_score = sum(int_value(record.get("score")) for record in records)
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


def mastery_item_summary(record: dict, points_by_id: dict[str, dict], item_type: str) -> dict:
    point_id = str(record.get("point_id") or "")
    point = points_by_id.get(point_id, {})
    return {
        "id": point_id,
        "type": item_type,
        "title": str(point.get("title") or point_id or "未命名知识点"),
        "score": int_value(record.get("score")),
        "level": str(record.get("level") or ""),
        "attempts": int_value(record.get("attempts")),
        "wrong_count": int_value(record.get("wrong_count")),
        "next_review_at": str(record.get("next_review_at") or ""),
    }
