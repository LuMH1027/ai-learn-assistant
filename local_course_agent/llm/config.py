from __future__ import annotations

from typing import Dict

from local_course_agent.config import normalize_ai_config, resolve_siliconflow_api_key
from local_course_agent.llm.client import OpenAICompatibleClient


def create_llm_client(ai_config: Dict):
    retry_callback = (ai_config or {}).get("__retry_callback__") if isinstance(ai_config, dict) else None
    ai_config = normalize_ai_config(ai_config)
    return OpenAICompatibleClient(
        base_url=ai_config.get("base_url"),
        api_key=resolve_siliconflow_api_key(ai_config.get("api_key")),
        model=ai_config.get("model"),
        retry_callback=retry_callback if callable(retry_callback) else None,
    )
