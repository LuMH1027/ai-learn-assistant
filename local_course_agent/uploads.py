from __future__ import annotations

import re
import time
from pathlib import Path

from local_course_agent.scanner import SUPPORTED_EXTENSIONS

MAX_UPLOAD_FILE_BYTES = 25 * 1024 * 1024
MAX_TOTAL_UPLOAD_BYTES = 64 * 1024 * 1024
CHAT_UPLOAD_MAX_FILES = 80
CHAT_UPLOAD_MAX_AGE_SECONDS = 7 * 24 * 60 * 60


def safe_upload_name(filename: str) -> str:
    normalized = filename.replace("\\", "/").split("/")[-1].strip()
    normalized = re.sub(r"[\x00-\x1f]", "", normalized)
    return normalized or "uploaded-file"


def save_course_upload(course_dir: Path, filename: str, content: bytes) -> Path:
    validate_upload_size(content)
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
    validate_upload_size(content)
    name = safe_upload_name(filename)
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(f"暂不支持该文件类型: {suffix or '无扩展名'}")
    target_dir = Path(data_dir) / "chat_uploads" / course_id
    target_dir.mkdir(parents=True, exist_ok=True)
    target = unique_path(target_dir / name)
    target.write_bytes(content)
    cleanup_chat_uploads(target_dir)
    return target


def validate_upload_size(content: bytes) -> None:
    if len(content) > MAX_UPLOAD_FILE_BYTES:
        limit_mb = MAX_UPLOAD_FILE_BYTES // (1024 * 1024)
        raise ValueError(f"文件过大，单个文件不能超过 {limit_mb} MB")


def cleanup_chat_uploads(target_dir: Path, max_files: int = CHAT_UPLOAD_MAX_FILES, max_age_seconds: int = CHAT_UPLOAD_MAX_AGE_SECONDS) -> None:
    files = [path for path in Path(target_dir).iterdir() if path.is_file()]
    if not files:
        return

    now = time.time()
    for path in files:
        try:
            if now - path.stat().st_mtime > max_age_seconds:
                path.unlink()
        except OSError:
            continue
    remaining = sorted(
        (path for path in Path(target_dir).iterdir() if path.is_file()),
        key=lambda path: path.stat().st_mtime,
    )
    for path in remaining[:-max_files]:
        try:
            path.unlink()
        except OSError:
            continue


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
