from __future__ import annotations

from copy import deepcopy
from hashlib import sha1
from typing import Any

from local_course_agent.learning.mastery.policy import (
    DEFAULT_MASTERY_SCORE,
    clamp_score,
    mastery_level,
    now_text,
    review_suggestion,
)

SCHEMA_VERSION = 1


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


def create_mastery_record(
    point_id: str,
    score: int = DEFAULT_MASTERY_SCORE,
    timestamp: str | None = None,
) -> dict:
    now = timestamp or now_text()
    normalized_score = clamp_score(score)
    review = review_suggestion(normalized_score, correct=None, timestamp=now)
    return {
        "point_id": str(point_id),
        "score": normalized_score,
        "level": mastery_level(normalized_score),
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


def positive_int(value: Any) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0
