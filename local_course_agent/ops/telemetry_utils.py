from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


def duration_summary(values: List[float]) -> Dict:
    if not values:
        return {"count": 0, "total": 0.0, "min": None, "max": None, "avg": None}
    total = sum(values)
    return {
        "count": len(values),
        "total": round(total, 3),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
        "avg": round(total / len(values), 3),
    }


def observation_summary(observations: Sequence[Any]) -> Dict[str, Dict]:
    grouped: Dict[str, List[float]] = {}
    for observation in observations:
        grouped.setdefault(observation.name, []).append(observation.value)
    return {name: numeric_summary(values) for name, values in sorted(grouped.items())}


def numeric_summary(values: List[float]) -> Dict:
    if not values:
        return {"count": 0, "min": None, "max": None, "avg": None, "distribution": {}}
    total = sum(values)
    distribution: Dict[str, int] = {}
    for value in values:
        bucket = str(int(value)) if value.is_integer() else str(value)
        distribution[bucket] = distribution.get(bucket, 0) + 1
    return {
        "count": len(values),
        "min": min(values),
        "max": max(values),
        "avg": round(total / len(values), 3),
        "distribution": dict(sorted(distribution.items(), key=lambda item: float(item[0]))),
    }


def counter_key(stage: str, name: str) -> str:
    return f"{normalize_stage(stage)}:{require_name(name, 'counter name')}"


def normalize_stage(stage: str) -> str:
    return str(stage or "general")


def require_name(name: str, label: str) -> str:
    normalized = str(name or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required")
    return normalized


def first_present(payload: Mapping[str, Any], keys: Iterable[str]) -> Any:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


def number_from_payload(payload: Mapping[str, Any], keys: Iterable[str]) -> Optional[float]:
    value = first_present(payload, keys)
    if value is None:
        return None
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return float(len(value))
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def bool_from_payload(payload: Mapping[str, Any], keys: Iterable[str]) -> Optional[bool]:
    value = first_present(payload, keys)
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1", "ok", "sufficient"}:
            return True
        if normalized in {"false", "no", "0", "insufficient", "empty"}:
            return False
    return bool(value)


def sequence_from_payload(payload: Mapping[str, Any], keys: Iterable[str]) -> Optional[Sequence]:
    value = first_present(payload, keys)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return None


def status_from_payload(payload: Mapping[str, Any]) -> str:
    status = first_present(payload, ("status", "llm_status"))
    if isinstance(status, str):
        normalized = status.strip().lower()
        if normalized in {"error", "failed", "failure", "timeout"}:
            return "error"
        if normalized in {"ok", "success", "succeeded", "completed", "ready"}:
            return "ok"
    if first_present(payload, ("error", "error_message")):
        return "error"
    return "ok"


def observe_if_number(recorder: Any, name: str, value: Optional[float], stage: str) -> None:
    if value is not None:
        recorder.observe(name, value, stage=stage)


def compact_attributes(attributes: Mapping[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in attributes.items() if value is not None and value != []}


def collect_trace_values(trace: Optional[Sequence], key: str, limit: int = 8) -> List[Any]:
    if not trace:
        return []
    values: List[Any] = []
    seen = set()
    for item in trace:
        if not isinstance(item, Mapping):
            continue
        value = item.get(key)
        if value is None or value in seen:
            continue
        seen.add(value)
        values.append(value)
        if len(values) >= limit:
            break
    return values


_duration_summary = duration_summary
_observation_summary = observation_summary
_numeric_summary = numeric_summary
_counter_key = counter_key
_normalize_stage = normalize_stage
_require_name = require_name
_first_present = first_present
_number_from_payload = number_from_payload
_bool_from_payload = bool_from_payload
_sequence_from_payload = sequence_from_payload
_status_from_payload = status_from_payload
_observe_if_number = observe_if_number
_compact_attributes = compact_attributes
_collect_trace_values = collect_trace_values
