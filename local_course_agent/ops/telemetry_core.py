from __future__ import annotations

import json
import time
from contextlib import AbstractContextManager
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Mapping, Optional

from local_course_agent.ops.telemetry_utils import (
    counter_key,
    duration_summary,
    normalize_stage,
    observation_summary,
    require_name,
)


Clock = Callable[[], float]


@dataclass
class TelemetryEvent:
    name: str
    stage: str
    timestamp: float
    attributes: Dict = field(default_factory=dict)


@dataclass
class TelemetrySpan:
    name: str
    stage: str
    started_at: float
    ended_at: Optional[float] = None
    duration_ms: Optional[float] = None
    status: str = "running"
    attributes: Dict = field(default_factory=dict)


@dataclass
class TelemetryCounter:
    name: str
    stage: str
    value: float = 0.0


@dataclass
class TelemetryObservation:
    name: str
    stage: str
    value: float
    timestamp: float
    attributes: Dict = field(default_factory=dict)


class TelemetryRecorder:
    """In-memory telemetry buffer for request-local or job-local diagnostics."""

    def __init__(self, clock: Optional[Clock] = None):
        self._clock = clock or time.monotonic
        self.events: List[TelemetryEvent] = []
        self.spans: List[TelemetrySpan] = []
        self.counters: Dict[str, TelemetryCounter] = {}
        self.observations: List[TelemetryObservation] = []

    def event(self, name: str, stage: str = "general", attributes: Optional[Mapping] = None) -> TelemetryEvent:
        event = TelemetryEvent(
            name=require_name(name, "event name"),
            stage=normalize_stage(stage),
            timestamp=self._clock(),
            attributes=dict(attributes or {}),
        )
        self.events.append(event)
        return event

    def increment(self, name: str, amount: float = 1.0, stage: str = "general") -> TelemetryCounter:
        if amount < 0:
            raise ValueError("counter amount must be non-negative")
        key = counter_key(stage, name)
        counter = self.counters.get(key)
        if counter is None:
            counter = TelemetryCounter(name=require_name(name, "counter name"), stage=normalize_stage(stage))
            self.counters[key] = counter
        counter.value += float(amount)
        return counter

    def observe(
        self,
        name: str,
        value: float,
        stage: str = "general",
        attributes: Optional[Mapping] = None,
    ) -> TelemetryObservation:
        observation = TelemetryObservation(
            name=require_name(name, "observation name"),
            stage=normalize_stage(stage),
            value=float(value),
            timestamp=self._clock(),
            attributes=dict(attributes or {}),
        )
        self.observations.append(observation)
        return observation

    def span(self, name: str, stage: str = "general", attributes: Optional[Mapping] = None) -> "_SpanContext":
        return _SpanContext(
            recorder=self,
            span=TelemetrySpan(
                name=require_name(name, "span name"),
                stage=normalize_stage(stage),
                started_at=self._clock(),
                attributes=dict(attributes or {}),
            ),
        )

    def to_dict(self) -> Dict:
        return {
            "events": [asdict(event) for event in self.events],
            "spans": [asdict(span) for span in self.spans],
            "counters": [asdict(counter) for counter in self.counters.values()],
            "observations": [asdict(observation) for observation in self.observations],
            "summary": self.summary_by_stage(),
        }

    def to_json(self, indent: Optional[int] = 2) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    def summary_by_stage(self) -> Dict[str, Dict]:
        stages = sorted(
            {
                event.stage
                for event in self.events
            }
            | {span.stage for span in self.spans}
            | {counter.stage for counter in self.counters.values()}
            | {observation.stage for observation in self.observations}
        )
        return {stage: self._summarize_stage(stage) for stage in stages}

    def _summarize_stage(self, stage: str) -> Dict:
        spans = [span for span in self.spans if span.stage == stage]
        events = [event for event in self.events if event.stage == stage]
        counters = {
            counter.name: counter.value
            for counter in self.counters.values()
            if counter.stage == stage
        }
        observations = [observation for observation in self.observations if observation.stage == stage]
        return {
            "event_count": len(events),
            "span_count": len(spans),
            "error_span_count": sum(1 for span in spans if span.status == "error"),
            "duration_ms": duration_summary([span.duration_ms for span in spans if span.duration_ms is not None]),
            "counters": counters,
            "observations": observation_summary(observations),
        }

    def _finish_span(self, span: TelemetrySpan, status: str, attributes: Optional[Mapping] = None) -> TelemetrySpan:
        ended_at = self._clock()
        span.ended_at = ended_at
        span.duration_ms = round(max(0.0, ended_at - span.started_at) * 1000, 3)
        span.status = status
        if attributes:
            span.attributes.update(dict(attributes))
        self.spans.append(span)
        return span


class _SpanContext(AbstractContextManager):
    def __init__(self, recorder: TelemetryRecorder, span: TelemetrySpan):
        self._recorder = recorder
        self.span = span
        self._finished = False

    def __enter__(self) -> TelemetrySpan:
        return self.span

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc_type is None:
            self.finish("ok")
            return False
        self.finish(
            "error",
            {
                "error_type": exc_type.__name__,
                "error_message": str(exc),
            },
        )
        return False

    def finish(self, status: str = "ok", attributes: Optional[Mapping] = None) -> TelemetrySpan:
        if self._finished:
            return self.span
        if status not in {"ok", "error"}:
            raise ValueError("span status must be 'ok' or 'error'")
        self._finished = True
        return self._recorder._finish_span(self.span, status, attributes)


__all__ = [
    "Clock",
    "TelemetryEvent",
    "TelemetrySpan",
    "TelemetryCounter",
    "TelemetryObservation",
    "TelemetryRecorder",
]
