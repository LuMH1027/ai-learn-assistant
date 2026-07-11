from __future__ import annotations

import re
from pathlib import Path

from local_course_agent.scanner import SUPPORTED_EXTENSIONS


def safe_upload_name(filename: str) -> str:
    normalized = filename.replace("\\", "/").split("/")[-1].strip()
    normalized = re.sub(r"[\x00-\x1f]", "", normalized)
    return normalized or "uploaded-file"


def save_course_upload(course_dir: Path, filename: str, content: bytes) -> Path:
    name = safe_upload_name(filename)
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"暂不支持该文件类型: {suffix or '无扩展名'}")
    target_dir = Path(course_dir) / "拖入资料"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = unique_path(target_dir / name)
    target.write_bytes(content)
    return target


def save_chat_upload(data_dir: Path, course_id: str, filename: str, content: bytes) -> Path:
    name = safe_upload_name(filename)
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"暂不支持该文件类型: {suffix or '无扩展名'}")
    target_dir = Path(data_dir) / "chat_uploads" / course_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = unique_path(target_dir / name)
    target.write_bytes(content)
    return target


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    for index in range(2, 1000):
        candidate = path.with_name(f"{stem}-{index}{suffix}")
        if not candidate.exists():
            return candidate
    raise ValueError("同名文件过多，请重命名后重试")

