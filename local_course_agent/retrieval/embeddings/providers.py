from __future__ import annotations

from local_course_agent.retrieval.embeddings.fake import FakeEmbeddingModel
from local_course_agent.retrieval.embeddings.openai import OpenAICompatibleEmbeddingModel


__all__ = ["FakeEmbeddingModel", "OpenAICompatibleEmbeddingModel"]
