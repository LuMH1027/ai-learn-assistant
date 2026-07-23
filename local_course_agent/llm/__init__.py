from __future__ import annotations

from local_course_agent.llm.client import LLMRequestError, OpenAICompatibleClient
from local_course_agent.llm.config import create_llm_client
from local_course_agent.llm.images import image_to_data_url
from local_course_agent.llm.prompts import build_course_summary_prompt, build_grounded_prompt

__all__ = [
    "OpenAICompatibleClient",
    "LLMRequestError",
    "build_course_summary_prompt",
    "build_grounded_prompt",
    "create_llm_client",
    "image_to_data_url",
]
