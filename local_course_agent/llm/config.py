from __future__ import annotations

from typing import Dict

from local_course_agent.config import SILICONFLOW_BASE_URL, SILICONFLOW_CHAT_MODEL, resolve_siliconflow_api_key
from local_course_agent.llm.client import OpenAICompatibleClient


def create_llm_client(ai_config: Dict):
    ai_config = dict(ai_config or {})
    return OpenAICompatibleClient(
        base_url=ai_config.get("base_url") or SILICONFLOW_BASE_URL,
        api_key=resolve_siliconflow_api_key(ai_config.get("api_key")),
        model=ai_config.get("model") or SILICONFLOW_CHAT_MODEL,
    )
