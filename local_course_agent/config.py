from __future__ import annotations

import json
from pathlib import Path
from typing import Dict


DEFAULT_CONFIG = {
    "root_folder": "",
    "ai": {
        "provider": "openai_compatible",
        "base_url": "",
        "api_key": "",
        "model": "",
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
        "mineru": dict(DEFAULT_CONFIG["mineru"]),
    }
    if isinstance(raw.get("ai"), dict):
        config["ai"].update(raw["ai"])
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
