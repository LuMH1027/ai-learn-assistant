from __future__ import annotations

from typing import Any, Dict, Mapping, Sequence


KNOWN_LLM_STATUSES = {
    "used",
    "fallback",
    "disabled",
    "skipped",
    "failed",
    "empty",
    "client_error",
    "summary_error",
}
KNOWN_WEB_STATUSES = {"used", "empty", "failed", "disabled", "skipped", "clarification"}
KNOWN_SUMMARY_METHODS = {"map_reduce", "single_prompt", "extractive"}


def summarize_quality_results(results: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    total = len(results)
    passed = sum(1 for item in results if item.get("passed"))
    failed_checks: Dict[str, int] = {}
    for item in results:
        for check in item.get("checks", []):
            if isinstance(check, Mapping) and not check.get("passed"):
                name = str(check.get("name") or "unknown")
                failed_checks[name] = failed_checks.get(name, 0) + 1
    return {
        "total_cases": total,
        "passed_cases": passed,
        "pass_rate": rate(passed, total),
        "failed_checks": failed_checks,
    }


def quality_result(checks: Sequence[Mapping[str, Any]], metrics: Mapping[str, Any]) -> Dict[str, Any]:
    failed = [check for check in checks if not check.get("passed")]
    return {
        "passed": not failed,
        "checks": list(checks),
        "failed_checks": failed,
        "metrics": dict(metrics),
    }


def as_list(value: Any) -> list:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return list(value)
    return []


def rate(value: int, total: int) -> float:
    return round(value / total, 4) if total else 0.0
