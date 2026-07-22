from __future__ import annotations

import json
from pathlib import Path
from typing import List

from local_course_agent.retrieval.evaluation.schema import RagEvalCase


def load_eval_cases(path: Path) -> List[RagEvalCase]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    raw_cases = payload.get("cases", payload) if isinstance(payload, dict) else payload
    if not isinstance(raw_cases, list):
        raise ValueError("RAG eval cases must be a JSON list or an object with a 'cases' list.")
    return [RagEvalCase.from_dict(item) for item in raw_cases]


__all__ = ["load_eval_cases"]
