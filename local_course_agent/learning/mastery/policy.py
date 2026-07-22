from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

DEFAULT_MASTERY_SCORE = 50
MIN_MASTERY_SCORE = 0
MAX_MASTERY_SCORE = 100

DIFFICULTY_WEIGHTS = {
    "easy": 0.75,
    "normal": 1.0,
    "hard": 1.25,
}


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
