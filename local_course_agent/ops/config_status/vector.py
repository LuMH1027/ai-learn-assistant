from __future__ import annotations

from pathlib import Path
from typing import Dict, Mapping

from local_course_agent.ops.config_status.model import capability
from local_course_agent.retrieval.vector_index import create_embedding_model


def vector_status(index_dir: Path, ai_config: Mapping) -> Dict:
    model = create_embedding_model(ai_config)
    vector_files = sorted(index_dir.glob("*.vector.json")) if index_dir.exists() else []
    real_provider = str(model.model_id).startswith("openai-compatible:")
    detail = (
        "已配置真实 embedding provider，可用于持久向量索引和混合检索。"
        if real_provider
        else "使用本地确定性 embedding，可离线运行；在 data/config.json 中配置 embedding 后可启用真实 embedding。"
    )
    if vector_files:
        detail = f"{detail} 检测到 {len(vector_files)} 个持久化向量索引。"
    return capability(
        "vector",
        "向量检索",
        "ok",
        True,
        detail,
        [],
        {
            "model": model.model_id,
            "dimensions": model.dimensions,
            "index_files": len(vector_files),
            "provider": "openai_compatible" if real_provider else "local",
        },
    )
