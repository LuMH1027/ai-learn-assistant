from __future__ import annotations

from local_course_agent.learning.mastery.policy import (
    DEFAULT_MASTERY_SCORE,
    DIFFICULTY_WEIGHTS,
    MAX_MASTERY_SCORE,
    MIN_MASTERY_SCORE,
    clamp_float,
    clamp_score,
    format_time,
    mastery_level,
    now_text,
    parse_time,
    review_suggestion,
    score_delta,
)
from local_course_agent.learning.mastery.schema import (
    SCHEMA_VERSION,
    clean_text,
    create_knowledge_point,
    create_mastery_record,
    create_mastery_state,
    create_mistake_record,
    merge_refs,
    merge_unique,
    normalize_knowledge_point,
    normalize_mastery_record,
    normalize_mistake_record,
    normalize_ref,
    normalize_refs,
    normalize_state,
    normalize_text_list,
    positive_int,
    stable_id,
)


def upsert_knowledge_point(state: dict, point: dict, timestamp: str | None = None) -> dict:
    next_state = normalize_state(state, timestamp=timestamp)
    now = timestamp or now_text()
    normalized = normalize_knowledge_point(point, timestamp=now)
    points = next_state["knowledge_points"]
    existing_index = next((index for index, item in enumerate(points) if item["id"] == normalized["id"]), None)
    if existing_index is None:
        points.append(normalized)
    else:
        existing = points[existing_index]
        merged = {
            **existing,
            **normalized,
            "created_at": existing.get("created_at") or normalized["created_at"],
            "aliases": merge_unique(existing.get("aliases", []), normalized.get("aliases", [])),
            "source_refs": merge_refs(existing.get("source_refs", []), normalized.get("source_refs", [])),
            "updated_at": now,
        }
        points[existing_index] = merged
    next_state["mastery"].setdefault(normalized["id"], create_mastery_record(normalized["id"], timestamp=now))
    next_state["updated_at"] = now
    return next_state


def apply_answer_result(
    state: dict,
    point_id: str,
    correct: bool,
    question: str = "",
    user_answer: str = "",
    expected_answer: str = "",
    difficulty: str = "normal",
    confidence: float | None = None,
    source_ref: dict | None = None,
    timestamp: str | None = None,
) -> dict:
    next_state = normalize_state(state, timestamp=timestamp)
    now = timestamp or now_text()
    normalized_point_id = str(point_id)
    current = next_state["mastery"].get(normalized_point_id) or create_mastery_record(normalized_point_id, timestamp=now)
    updated = update_mastery_for_answer(
        current,
        correct=correct,
        difficulty=difficulty,
        confidence=confidence,
        timestamp=now,
    )
    next_state["mastery"][normalized_point_id] = updated["mastery"]
    if not correct:
        mistake = create_mistake_record(
            point_id=normalized_point_id,
            question=question,
            user_answer=user_answer,
            expected_answer=expected_answer,
            source_ref=source_ref,
            timestamp=now,
        )
        next_state["mistakes"].append(mistake)
    next_state["updated_at"] = now
    next_state["last_update"] = {
        "point_id": normalized_point_id,
        "correct": bool(correct),
        "score_delta": updated["score_delta"],
        "review": updated["review"],
    }
    return next_state


def update_mastery_for_answer(
    record: dict,
    correct: bool,
    difficulty: str = "normal",
    confidence: float | None = None,
    timestamp: str | None = None,
) -> dict:
    now = timestamp or now_text()
    current = normalize_mastery_record(record, timestamp=now)
    delta = score_delta(
        correct=correct,
        difficulty=difficulty,
        confidence=confidence,
        current_score=current["score"],
        streak=current["streak"],
    )
    next_score = clamp_score(current["score"] + delta)
    next_streak = current["streak"] + 1 if correct else 0
    review = review_suggestion(next_score, correct=correct, timestamp=now)
    next_record = {
        **current,
        "score": next_score,
        "level": mastery_level(next_score),
        "attempts": current["attempts"] + 1,
        "correct_count": current["correct_count"] + (1 if correct else 0),
        "wrong_count": current["wrong_count"] + (0 if correct else 1),
        "streak": next_streak,
        "last_result": "correct" if correct else "wrong",
        "last_answered_at": now,
        "next_review_at": review["next_review_at"],
        "review_interval_days": review["interval_days"],
        "updated_at": now,
    }
    return {
        "mastery": next_record,
        "score_delta": delta,
        "review": review,
    }


def resolve_mistake(mistake: dict, timestamp: str | None = None) -> dict:
    now = timestamp or now_text()
    normalized = normalize_mistake_record(mistake, timestamp=now)
    normalized["status"] = "resolved"
    normalized["review_count"] = normalized["review_count"] + 1
    normalized["updated_at"] = now
    normalized["resolved_at"] = now
    return normalized
