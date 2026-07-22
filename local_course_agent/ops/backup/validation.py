from __future__ import annotations

import json
import posixpath
import zipfile
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable

from .schema import ALLOWED_BACKUP_FILES, ALLOWED_BACKUP_ROOTS, MANIFEST_NAME


def read_manifest(archive: zipfile.ZipFile) -> Dict:
    try:
        return json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
    except KeyError as exc:
        raise ValueError("Backup archive is missing manifest.json.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Backup manifest is not valid UTF-8 JSON.") from exc


def validate_archive_members(infos: Iterable[zipfile.ZipInfo]) -> None:
    names = [info.filename for info in infos]
    if MANIFEST_NAME not in names:
        raise ValueError("Backup archive is missing manifest.json.")
    for name in names:
        if name == MANIFEST_NAME or name.endswith("/"):
            continue
        validate_member_path(name)
        if not is_allowed_backup_path(name):
            raise ValueError(f"Backup member is outside allowed data paths: {name}")


def validate_member_path(name: str) -> None:
    normalized = posixpath.normpath(name)
    parts = PurePosixPath(name).parts
    if name.startswith("/") or name.startswith("\\"):
        raise ValueError(f"Unsafe absolute backup member path: {name}")
    if "\\" in name:
        raise ValueError(f"Unsafe backup member path separator: {name}")
    if normalized in ("", ".") or normalized.startswith("../") or ".." in parts:
        raise ValueError(f"Unsafe backup member path traversal: {name}")
    if normalized != name:
        raise ValueError(f"Unsafe non-normal backup member path: {name}")


def is_allowed_backup_path(name: str) -> bool:
    return name in ALLOWED_BACKUP_FILES or any(name.startswith(f"{root}/") for root in ALLOWED_BACKUP_ROOTS)


def safe_destination(target: Path, archive_name: str) -> Path:
    validate_member_path(archive_name)
    destination = target / archive_name
    resolved_target = target.resolve()
    resolved_destination = destination.resolve()
    if resolved_destination != resolved_target and resolved_target not in resolved_destination.parents:
        raise ValueError(f"Backup member escapes target directory: {archive_name}")
    return destination


def member_info(info: zipfile.ZipInfo) -> Dict:
    return {
        "path": info.filename,
        "size": info.file_size,
        "compressed_size": info.compress_size,
        "is_dir": info.is_dir(),
    }
