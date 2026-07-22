from __future__ import annotations

from typing import Any, Mapping, Sequence

from local_course_agent.config import (
    SILICONFLOW_BASE_URL,
    SILICONFLOW_EMBEDDING_MODEL,
    resolve_siliconflow_api_key,
)
from local_course_agent.retrieval.embeddings.models import EmbeddingModel
from local_course_agent.retrieval.embeddings.providers import FakeEmbeddingModel, OpenAICompatibleEmbeddingModel
from local_course_agent.retrieval.embeddings.utils import (
    DEFAULT_DIMENSIONS,
    DEFAULT_EMBEDDING_BATCH_SIZE,
    DEFAULT_EMBEDDING_MAX_RETRIES,
    DEFAULT_EMBEDDING_RETRY_DELAY,
)


def create_embedding_model(config: Mapping[str, Any] | None = None) -> EmbeddingModel:
    config = dict(config or {})
    embedding_model = str(config.get("embedding_model") or SILICONFLOW_EMBEDDING_MODEL).strip()
    api_key = resolve_siliconflow_api_key(config.get("embedding_api_key"), config.get("api_key"))
    base_url = str(config.get("embedding_base_url") or config.get("base_url") or SILICONFLOW_BASE_URL).strip()
    if embedding_model and api_key and base_url:
        return OpenAICompatibleEmbeddingModel(
            base_url=base_url,
            api_key=api_key,
            model=embedding_model,
            dimensions=optional_int(config.get("embedding_dimensions")),
            timeout=config_float(config, ("embedding_timeout", "timeout"), 30.0),
            batch_size=config_int(config, ("embedding_batch_size", "batch_size"), DEFAULT_EMBEDDING_BATCH_SIZE),
            max_retries=config_int(
                config,
                ("embedding_max_retries", "max_retries"),
                DEFAULT_EMBEDDING_MAX_RETRIES,
            ),
            retry_delay=config_float(
                config,
                ("embedding_retry_delay", "retry_delay"),
                DEFAULT_EMBEDDING_RETRY_DELAY,
            ),
        )
    return FakeEmbeddingModel(dimensions=config_int(config, ("fake_embedding_dimensions",), DEFAULT_DIMENSIONS))


def optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def config_int(config: Mapping[str, Any], keys: Sequence[str], default: int) -> int:
    for key in keys:
        value = config.get(key)
        if value not in (None, ""):
            return int(value)
    return default


def config_float(config: Mapping[str, Any], keys: Sequence[str], default: float) -> float:
    for key in keys:
        value = config.get(key)
        if value not in (None, ""):
            return float(value)
    return default
