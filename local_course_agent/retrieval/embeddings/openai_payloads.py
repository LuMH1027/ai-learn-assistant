from __future__ import annotations

import json
from typing import List, Mapping, Sequence

from local_course_agent.retrieval.embeddings.models import EmbeddingRequestError


def build_embedding_payload(model: str, items: Sequence[str]) -> bytes:
    return json.dumps({"model": model, "input": list(items)}).encode("utf-8")


def parse_embedding_response(
    raw: str,
    *,
    endpoint: str,
    expected_count: int,
    batch_number: int,
) -> List[List[float]]:
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EmbeddingRequestError(
            f"embedding response JSON decode failed for {endpoint} (batch {batch_number}): {exc.msg}"
        ) from exc
    if not isinstance(parsed, Mapping):
        raise EmbeddingRequestError(
            f"embedding response schema error for {endpoint} (batch {batch_number}): expected JSON object"
        )
    data = parsed.get("data")
    if not isinstance(data, list):
        raise EmbeddingRequestError(
            f"embedding response schema error for {endpoint} (batch {batch_number}): missing data list"
        )
    try:
        sorted_data = sorted(data, key=lambda item: int(item.get("index", 0)))
        vectors = [[float(value) for value in item.get("embedding", [])] for item in sorted_data]
    except (AttributeError, TypeError, ValueError) as exc:
        raise EmbeddingRequestError(
            f"embedding response schema error for {endpoint} (batch {batch_number}): invalid data item"
        ) from exc
    if len(vectors) != expected_count:
        raise EmbeddingRequestError(
            f"embedding response count mismatch for {endpoint} "
            f"(batch {batch_number}): expected {expected_count}, got {len(vectors)}"
        )
    if not vectors or not vectors[0]:
        raise EmbeddingRequestError(f"embedding response is empty for {endpoint} (batch {batch_number})")
    dimensions = len(vectors[0])
    for vector in vectors:
        if len(vector) != dimensions:
            raise EmbeddingRequestError(
                f"embedding response dimension mismatch within batch {batch_number}: "
                f"expected {dimensions}, got {len(vector)}"
            )
    return vectors
