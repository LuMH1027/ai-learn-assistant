from __future__ import annotations

from hashlib import sha1

from local_course_agent.learning.mastery.normalization import (
    SCHEMA_VERSION,
    clean_text,
    normalize_ref,
    normalize_refs,
    normalize_text_list,
    stable_id,
)
from local_course_agent.learning.mastery.policy import (
    DEFAULT_MASTERY_SCORE,
    clamp_score,
    mastery_level,
    now_text,
    review_suggestion,
)


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
