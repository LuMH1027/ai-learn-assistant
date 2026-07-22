from __future__ import annotations

from typing import Any, Dict, Mapping, Optional

from local_course_agent.evaluation.demo_fixtures import (
    DEMO_DATA_STRUCTURE_COURSE_ID,
    DEMO_OS_COURSE_ID,
)


def quality_case_result(
    case_id: str,
    course_id: str,
    quality: Mapping[str, Any],
    extra: Optional[Mapping[str, Any]] = None,
) -> Dict:
    result = {
        "id": case_id,
        "course_id": course_id,
        "passed": quality["passed"],
        "checks": quality["checks"],
        "failed_checks": quality["failed_checks"],
        "metrics": quality["metrics"],
    }
    result.update(extra or {})
    return result


def summary_case_result(case_id: str, course_id: str, payload: Mapping[str, Any], quality: Mapping[str, Any]) -> Dict:
    return quality_case_result(
        case_id=case_id,
        course_id=course_id,
        quality=quality,
        extra={
            "summary_method": payload.get("summary_method"),
            "llm_status": payload.get("llm_status"),
            "fallback_reason": payload.get("fallback_reason", ""),
        },
    )


def course_name(course_id: str) -> str:
    names = {
        DEMO_OS_COURSE_ID: "操作系统",
        DEMO_DATA_STRUCTURE_COURSE_ID: "数据结构",
    }
    return names.get(course_id, course_id)
