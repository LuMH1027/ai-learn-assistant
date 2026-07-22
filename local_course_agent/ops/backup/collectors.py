from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from .schema import ALLOWED_BACKUP_FILES, ALLOWED_BACKUP_ROOTS, BackupEntry


def collect_backup_entries(data_dir: Path) -> List[BackupEntry]:
    """Return the files that would be included in a backup."""
    root = Path(data_dir)
    entries = [_build_entry(path, root) for path in _iter_backup_files(root)]
    return sorted(entries, key=lambda item: item.path)


def _iter_backup_files(root: Path) -> Iterable[Path]:
    for relative in ALLOWED_BACKUP_FILES:
        path = root / relative
        if path.is_file():
            yield path
    for folder in ALLOWED_BACKUP_ROOTS:
        base = root / folder
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file():
                yield path


def _build_entry(path: Path, root: Path) -> BackupEntry:
    relative = path.relative_to(root).as_posix()
    return BackupEntry(
        path=relative,
        size=path.stat().st_size,
        sha256=_sha256(path),
        kind=_entry_kind(relative),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _entry_kind(relative_path: str) -> str:
    if relative_path == "config.example.json":
        return "config_example"
    if relative_path.startswith("course_memory/"):
        return "course_memory"
    if relative_path.startswith("indexes/"):
        return "index"
    return "unknown"


def collect_index_schema_versions(root: Path, entries: Iterable[BackupEntry]) -> Dict[str, Optional[int]]:
    versions: Dict[str, Optional[int]] = {}
    for entry in entries:
        if entry.kind != "index" or not entry.path.endswith(".json"):
            continue
        try:
            payload = json.loads((root / entry.path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            versions[entry.path] = None
            continue
        schema_version = payload.get("schema_version") if isinstance(payload, dict) else None
        versions[entry.path] = schema_version if isinstance(schema_version, int) else None
    return versions
