from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Dict


SILICONFLOW_BASE_URL = "https://api.siliconflow.cn/v1"
SILICONFLOW_CHAT_MODEL = "Qwen/Qwen3.5-35B-A3B"
SILICONFLOW_EMBEDDING_MODEL = "Qwen/Qwen3-VL-Embedding-8B"
SILICONFLOW_RERANK_MODEL = "Qwen/Qwen3-Reranker-8B"
SILICONFLOW_API_KEY_ENV = "SILICONFLOW_API_KEY"


DEFAULT_CONFIG = {
    "root_folder": "",
    "ai": {
        "provider": "openai_compatible",
        "base_url": SILICONFLOW_BASE_URL,
        "api_key": "",
        "model": SILICONFLOW_CHAT_MODEL,
        "embedding_model": SILICONFLOW_EMBEDDING_MODEL,
        "embedding_dimensions": "",
        "embedding_base_url": SILICONFLOW_BASE_URL,
        "embedding_api_key": "",
        "embedding_timeout": 30,
        "embedding_batch_size": 32,
        "embedding_max_retries": 2,
        "embedding_retry_delay": 1.0,
        "rerank_model": SILICONFLOW_RERANK_MODEL,
        "rerank_base_url": SILICONFLOW_BASE_URL,
        "rerank_api_key": "",
        "rerank_timeout": 30,
        "rerank_top_n": 12,
    },
    "web_search": {
        "enabled": False,
        "provider": "mcp",
        "mcp_url": "",
        "tool_name": "",
        "query_argument": "query",
        "max_results_argument": "",
        "max_results": 5,
        "timeout": 20,
        "api_key": "",
        "auth_header": "Authorization",
        "auth_scheme": "Bearer",
    },
    "mineru": {
        "auto": True,
        "api_enabled": True,
        "command": "",
        "language": "ch",
        "token": "",
    },
}


def normalize_config(raw: Dict) -> Dict:
    config = {
        "root_folder": raw.get("root_folder", DEFAULT_CONFIG["root_folder"]),
        "ai": dict(DEFAULT_CONFIG["ai"]),
        "web_search": dict(DEFAULT_CONFIG["web_search"]),
        "mineru": dict(DEFAULT_CONFIG["mineru"]),
    }
    if isinstance(raw.get("ai"), dict):
        config["ai"].update(raw["ai"])
    if isinstance(raw.get("web_search"), dict):
        config["web_search"].update(raw["web_search"])
    if isinstance(raw.get("mineru"), dict):
        config["mineru"].update(raw["mineru"])

    if raw.get("mineru_command"):
        config["mineru"]["command"] = raw["mineru_command"]
    return config


def load_config(path: Path) -> Dict:
    if not path.exists():
        return normalize_config({})
    return normalize_config(json.loads(path.read_text(encoding="utf-8")))


def write_config(path: Path, config: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalize_config(config), ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_siliconflow_api_key(*values: object) -> str:
    for value in values:
        text = str(value or "").strip()
        if text.startswith("${") and text.endswith("}"):
            text = os.getenv(text[2:-1], "").strip()
        elif text.startswith("$") and len(text) > 1:
            text = os.getenv(text[1:], "").strip()
        if text:
            return text
    return os.getenv(SILICONFLOW_API_KEY_ENV, "").strip()
