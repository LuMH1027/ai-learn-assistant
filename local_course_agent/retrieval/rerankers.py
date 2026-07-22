from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Dict, List, Mapping, Protocol, Sequence


DEFAULT_RERANK_TOP_N = 12
DEFAULT_RERANK_TIMEOUT = 30.0


class RerankRequestError(RuntimeError):
    """Raised when an external rerank provider cannot return valid scores."""


class Reranker(Protocol):
    model_id: str

    def rerank(self, query: str, documents: Sequence[str], top_n: int | None = None) -> List[Dict[str, Any]]:
        ...


class NoopReranker:
    model_id = "local-rerank"

    def rerank(self, query: str, documents: Sequence[str], top_n: int | None = None) -> List[Dict[str, Any]]:
        return []


class SiliconFlowReranker:
    """SiliconFlow `/rerank` client for cross-encoder style candidate scoring."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float = DEFAULT_RERANK_TIMEOUT,
        default_top_n: int = DEFAULT_RERANK_TOP_N,
    ):
        if not base_url or not api_key or not model:
            raise ValueError("base_url, api_key, and model are required")
        if default_top_n <= 0:
            raise ValueError("default_top_n must be positive")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.model_id = f"siliconflow-rerank:{model}"
        self.timeout = float(timeout)
        self.default_top_n = int(default_top_n)

    def rerank(self, query: str, documents: Sequence[str], top_n: int | None = None) -> List[Dict[str, Any]]:
        items = [str(document) for document in documents]
        if not items:
            return []
        requested_top_n = min(int(top_n or self.default_top_n), len(items))
        payload = json.dumps(
            {
                "model": self.model,
                "query": query,
                "documents": items,
                "return_documents": True,
                "top_n": requested_top_n,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/rerank",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                parsed = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
            raise RerankRequestError(f"rerank request failed for {self.base_url}/rerank") from exc
        return parse_rerank_results(parsed)


def create_reranker(config: Mapping[str, Any] | None = None) -> Reranker:
    config = dict(config or {})
    model = str(config.get("rerank_model") or "").strip()
    api_key = str(config.get("rerank_api_key") or config.get("api_key") or "").strip()
    base_url = str(config.get("rerank_base_url") or config.get("base_url") or "").strip()
    if model and api_key and base_url:
        return SiliconFlowReranker(
            base_url=base_url,
            api_key=api_key,
            model=model,
            timeout=_config_float(config, ("rerank_timeout", "timeout"), DEFAULT_RERANK_TIMEOUT),
            default_top_n=_config_int(config, ("rerank_top_n",), DEFAULT_RERANK_TOP_N),
        )
    return NoopReranker()


def apply_external_rerank(
    candidates: Sequence[Dict],
    *,
    query: str,
    reranker: Reranker | None,
    top_n: int | None = None,
) -> List[Dict]:
    if reranker is None or isinstance(reranker, NoopReranker) or not candidates:
        return [dict(candidate) for candidate in candidates]
    documents = [candidate_text(candidate) for candidate in candidates]
    try:
        results = reranker.rerank(query, documents, top_n=top_n or len(documents))
    except RerankRequestError:
        return [dict(candidate) for candidate in candidates]
    by_index = {int(result["index"]): result for result in results if "index" in result}
    reranked = []
    for index, candidate in enumerate(candidates):
        item = dict(candidate)
        result = by_index.get(index)
        if result:
            score = float(result.get("score", 0.0))
            item["external_rerank_score"] = score
            item["rerank_model"] = getattr(reranker, "model_id", "")
            item["local_rerank_score"] = score
        reranked.append(item)
    return sorted(
        reranked,
        key=lambda item: (
            item.get("external_rerank_score", item.get("local_rerank_score", 0)),
            item.get("rrf_score", 0),
        ),
        reverse=True,
    )


def parse_rerank_results(payload: Mapping[str, Any]) -> List[Dict[str, Any]]:
    raw_results = payload.get("results") or payload.get("data") or []
    if not isinstance(raw_results, list):
        raise RerankRequestError("rerank response schema error: missing results list")
    parsed = []
    for item in raw_results:
        if not isinstance(item, Mapping):
            raise RerankRequestError("rerank response schema error: invalid result item")
        index = item.get("index")
        score = item.get("relevance_score", item.get("score"))
        if index is None or score is None:
            raise RerankRequestError("rerank response schema error: missing index or score")
        parsed.append({"index": int(index), "score": float(score), "document": item.get("document")})
    return parsed


def candidate_text(candidate: Mapping[str, Any]) -> str:
    section = str(candidate.get("section_title") or "").strip()
    file_name = str(candidate.get("file_name") or "").strip()
    text = str(candidate.get("context_text") or candidate.get("text") or "").strip()
    prefix = " ".join(part for part in (file_name, section) if part)
    return f"{prefix}\n{text}".strip()


def _config_int(config: Mapping[str, Any], keys: Sequence[str], default: int) -> int:
    for key in keys:
        value = config.get(key)
        if value not in (None, ""):
            return int(value)
    return default


def _config_float(config: Mapping[str, Any], keys: Sequence[str], default: float) -> float:
    for key in keys:
        value = config.get(key)
        if value not in (None, ""):
            return float(value)
    return default
