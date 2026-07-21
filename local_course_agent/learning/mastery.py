from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from hashlib import sha1
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_MASTERY_SCORE = 50
MIN_MASTERY_SCORE = 0
MAX_MASTERY_SCORE = 100

DIFFICULTY_WEIGHTS = {
    "easy": 0.75,
    "normal": 1.0,
    "hard": 1.25,
}


def create_mastery_state(timestamp: str | None = None) -> dict:
    now = timestamp or now_text()
    return {
        "schema_version": SCHEMA_VERSION,
        "knowledge_points": [],
        "mastery": {},
        "mistakes": [],
        "created_at": now,
        "updated_at": now,
    }


def create_knowledge_point(
    title: str,
    point_id: str | None = None,
    aliases: list[str] | None = None,
    source_refs: list[dict] | None = None,
    timestamp: str | None = None,
) -> dict:
    now = timestamp or now_text()
    normalized_title = clean_text(title, default="未命名知识点", limit=120)
    return {
        "id": point_id or stable_id(normalized_title),
        "title": normalized_title,
        "aliases": normalize_text_list(aliases or [], limit=12),
        "source_refs": normalize_refs(source_refs or []),
        "created_at": now,
        "updated_at": now,
    }


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


def create_mastery_record(
    point_id: str,
    score: int = DEFAULT_MASTERY_SCORE,
    timestamp: str | None = None,
) -> dict:
    now = timestamp or now_text()
    review = review_suggestion(clamp_score(score), correct=None, timestamp=now)
    return {
        "point_id": str(point_id),
        "score": clamp_score(score),
        "level": mastery_level(score),
        "attempts": 0,
        "correct_count": 0,
        "wrong_count": 0,
        "streak": 0,
        "last_result": "",
        "last_answered_at": "",
        "next_review_at": review["next_review_at"],
        "review_interval_days": review["interval_days"],
        "updated_at": now,
    }


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


def create_mistake_record(
    point_id: str,
    question: str,
    user_answer: str = "",
    expected_answer: str = "",
    source_ref: dict | None = None,
    timestamp: str | None = None,
) -> dict:
    now = timestamp or now_text()
    normalized_question = clean_text(question, default="未记录题目", limit=1000)
    identity = "|".join([str(point_id), normalized_question, now])
    return {
        "id": f"mistake-{sha1(identity.encode('utf-8')).hexdigest()[:12]}",
        "point_id": str(point_id),
        "question": normalized_question,
        "user_answer": clean_text(user_answer, default="", limit=1000),
        "expected_answer": clean_text(expected_answer, default="", limit=1000),
        "source_ref": normalize_ref(source_ref or {}),
        "status": "open",
        "review_count": 0,
        "created_at": now,
        "updated_at": now,
        "resolved_at": "",
    }


def resolve_mistake(mistake: dict, timestamp: str | None = None) -> dict:
    now = timestamp or now_text()
    normalized = normalize_mistake_record(mistake, timestamp=now)
    normalized["status"] = "resolved"
    normalized["review_count"] = normalized["review_count"] + 1
    normalized["updated_at"] = now
    normalized["resolved_at"] = now
    return normalized


def review_suggestion(score: int, correct: bool | None = None, timestamp: str | None = None) -> dict:
    base = parse_time(timestamp or now_text())
    normalized_score = clamp_score(score)
    if correct is False:
        interval_days = 1
        reason = "刚答错，建议明天优先复盘。"
    elif normalized_score < 40:
        interval_days = 1
        reason = "掌握度较低，需要短间隔复习。"
    elif normalized_score < 60:
        interval_days = 2
        reason = "掌握度不稳定，建议两天内再练一次。"
    elif normalized_score < 80:
        interval_days = 4
        reason = "掌握度中等，适合几天后巩固。"
    else:
        interval_days = 7
        reason = "掌握度较高，可以拉长复习间隔。"
    return {
        "next_review_at": format_time(base + timedelta(days=interval_days)),
        "interval_days": interval_days,
        "reason": reason,
    }


def mastery_level(score: int) -> str:
    normalized_score = clamp_score(score)
    if normalized_score < 40:
        return "weak"
    if normalized_score < 60:
        return "building"
    if normalized_score < 80:
        return "familiar"
    return "mastered"


def score_delta(
    correct: bool,
    difficulty: str = "normal",
    confidence: float | None = None,
    current_score: int = DEFAULT_MASTERY_SCORE,
    streak: int = 0,
) -> int:
    weight = DIFFICULTY_WEIGHTS.get(difficulty, DIFFICULTY_WEIGHTS["normal"])
    confidence_factor = 1.0 if confidence is None else 0.75 + (clamp_float(confidence) * 0.5)
    if correct:
        headroom = max(0.35, (MAX_MASTERY_SCORE - clamp_score(current_score)) / 100)
        streak_bonus = min(max(streak, 0), 3)
        return max(1, round((8 + streak_bonus) * weight * confidence_factor * headroom))
    penalty_room = max(0.5, clamp_score(current_score) / 100)
    return -max(4, round(12 * weight * confidence_factor * penalty_room))


def normalize_state(state: dict | None, timestamp: str | None = None) -> dict:
    now = timestamp or now_text()
    raw = deepcopy(state or {})
    points = [normalize_knowledge_point(point, timestamp=now) for point in raw.get("knowledge_points", [])]
    mastery = {}
    for point_id, record in dict(raw.get("mastery", {})).items():
        normalized = normalize_mastery_record({**dict(record), "point_id": point_id}, timestamp=now)
        mastery[normalized["point_id"]] = normalized
    mistakes = [normalize_mistake_record(item, timestamp=now) for item in raw.get("mistakes", [])]
    return {
        "schema_version": int(raw.get("schema_version") or SCHEMA_VERSION),
        "knowledge_points": points,
        "mastery": mastery,
        "mistakes": mistakes,
        "created_at": str(raw.get("created_at") or now),
        "updated_at": str(raw.get("updated_at") or now),
    }


def normalize_knowledge_point(point: dict, timestamp: str | None = None) -> dict:
    now = timestamp or now_text()
    title = clean_text(point.get("title", ""), default="未命名知识点", limit=120)
    return {
        "id": str(point.get("id") or stable_id(title)),
        "title": title,
        "aliases": normalize_text_list(point.get("aliases", []), limit=12),
        "source_refs": normalize_refs(point.get("source_refs", [])),
        "created_at": str(point.get("created_at") or now),
        "updated_at": str(point.get("updated_at") or now),
    }


def normalize_mastery_record(record: dict, timestamp: str | None = None) -> dict:
    now = timestamp or now_text()
    score = clamp_score(record.get("score", DEFAULT_MASTERY_SCORE))
    try:
        interval = int(record.get("review_interval_days", 1))
    except (TypeError, ValueError):
        interval = 1
    return {
        "point_id": str(record.get("point_id", "")),
        "score": score,
        "level": mastery_level(score),
        "attempts": positive_int(record.get("attempts", 0)),
        "correct_count": positive_int(record.get("correct_count", 0)),
        "wrong_count": positive_int(record.get("wrong_count", 0)),
        "streak": positive_int(record.get("streak", 0)),
        "last_result": str(record.get("last_result") or ""),
        "last_answered_at": str(record.get("last_answered_at") or ""),
        "next_review_at": str(record.get("next_review_at") or review_suggestion(score, timestamp=now)["next_review_at"]),
        "review_interval_days": max(interval, 1),
        "updated_at": str(record.get("updated_at") or now),
    }


def normalize_mistake_record(mistake: dict, timestamp: str | None = None) -> dict:
    now = timestamp or now_text()
    question = clean_text(mistake.get("question", ""), default="未记录题目", limit=1000)
    identity = "|".join([str(mistake.get("point_id", "")), question, str(mistake.get("created_at") or now)])
    status = str(mistake.get("status") or "open")
    if status not in {"open", "resolved"}:
        status = "open"
    return {
        "id": str(mistake.get("id") or f"mistake-{sha1(identity.encode('utf-8')).hexdigest()[:12]}"),
        "point_id": str(mistake.get("point_id", "")),
        "question": question,
        "user_answer": clean_text(mistake.get("user_answer", ""), default="", limit=1000),
        "expected_answer": clean_text(mistake.get("expected_answer", ""), default="", limit=1000),
        "source_ref": normalize_ref(mistake.get("source_ref", {})),
        "status": status,
        "review_count": positive_int(mistake.get("review_count", 0)),
        "created_at": str(mistake.get("created_at") or now),
        "updated_at": str(mistake.get("updated_at") or now),
        "resolved_at": str(mistake.get("resolved_at") or ""),
    }


def normalize_refs(refs: list[dict]) -> list[dict]:
    return [normalize_ref(ref) for ref in refs if isinstance(ref, dict)]


def normalize_ref(ref: dict) -> dict:
    return {
        key: str(value)
        for key, value in dict(ref).items()
        if key in {"file_id", "file_name", "section_title", "page", "chunk_id"} and value not in {None, ""}
    }


def merge_refs(left: list[dict], right: list[dict]) -> list[dict]:
    merged = []
    seen = set()
    for ref in normalize_refs(left) + normalize_refs(right):
        marker = tuple(sorted(ref.items()))
        if marker in seen:
            continue
        seen.add(marker)
        merged.append(ref)
    return merged


def merge_unique(left: list[str], right: list[str]) -> list[str]:
    values = []
    seen = set()
    for item in normalize_text_list(left + right, limit=24):
        if item in seen:
            continue
        seen.add(item)
        values.append(item)
    return values


def normalize_text_list(values: list[Any], limit: int) -> list[str]:
    result = []
    for value in values:
        text = clean_text(value, default="", limit=80)
        if text and text not in result:
            result.append(text)
        if len(result) >= limit:
            break
    return result


def stable_id(text: str) -> str:
    digest = sha1(text.strip().lower().encode("utf-8")).hexdigest()[:12]
    return f"kp-{digest}"


def clean_text(value: Any, default: str, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return default
    return text[:limit]


def clamp_score(value: Any) -> int:
    try:
        number = round(float(value))
    except (TypeError, ValueError):
        number = DEFAULT_MASTERY_SCORE
    return min(max(int(number), MIN_MASTERY_SCORE), MAX_MASTERY_SCORE)


def clamp_float(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.5
    return min(max(number, 0.0), 1.0)


def positive_int(value: Any) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def now_text() -> str:
    return format_time(datetime.now())


def parse_time(value: str) -> datetime:
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern)
        except ValueError:
            continue
    return datetime.now()


def format_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")
