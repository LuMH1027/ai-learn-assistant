from __future__ import annotations

import hashlib
import json
import posixpath
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Dict, Iterable, List, Optional


BACKUP_SCHEMA_VERSION = 1
MANIFEST_NAME = "manifest.json"
ALLOWED_BACKUP_ROOTS = ("course_memory", "indexes")
ALLOWED_BACKUP_FILES = ("config.example.json",)


@dataclass(frozen=True)
class BackupEntry:
    path: str
    size: int
    sha256: str
    kind: str

    def to_dict(self) -> Dict:
        return {
            "path": self.path,
            "size": self.size,
            "sha256": self.sha256,
            "kind": self.kind,
        }


@dataclass(frozen=True)
class BackupManifest:
    backup_schema_version: int
    created_at: str
    source_data_dir: str
    files: List[BackupEntry]
    index_schema_versions: Dict[str, Optional[int]] = field(default_factory=dict)
    migration: Dict = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "backup_schema_version": self.backup_schema_version,
            "created_at": self.created_at,
            "source_data_dir": self.source_data_dir,
            "files": [entry.to_dict() for entry in self.files],
            "index_schema_versions": dict(self.index_schema_versions),
            "migration": dict(self.migration),
        }


def collect_backup_entries(data_dir: Path) -> List[BackupEntry]:
    """Return the files that would be included in a backup."""
    root = Path(data_dir)
    entries = [_build_entry(path, root) for path in _iter_backup_files(root)]
    return sorted(entries, key=lambda item: item.path)


def build_manifest(data_dir: Path, entries: Optional[Iterable[BackupEntry]] = None) -> BackupManifest:
    root = Path(data_dir)
    file_entries = list(entries) if entries is not None else collect_backup_entries(root)
    return BackupManifest(
        backup_schema_version=BACKUP_SCHEMA_VERSION,
        created_at=datetime.now(timezone.utc).isoformat(),
        source_data_dir=str(root),
        files=file_entries,
        index_schema_versions=_collect_index_schema_versions(root, file_entries),
        migration={
            "index_schema_target": None,
            "index_schema_migrations": [],
        },
    )


def create_backup(data_dir: Path, zip_path: Path, dry_run: bool = False) -> Dict:
    """
    Create a zip backup for local course data.

    When dry_run is True, no zip file is written and the returned payload only
    describes what would be archived.
    """
    root = Path(data_dir)
    output = Path(zip_path)
    entries = collect_backup_entries(root)
    manifest = build_manifest(root, entries)
    if dry_run:
        return {
            "dry_run": True,
            "zip_path": str(output),
            "manifest": manifest.to_dict(),
            "files": [entry.to_dict() for entry in entries],
        }

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            MANIFEST_NAME,
            json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        )
        for entry in entries:
            archive.write(root / entry.path, entry.path)

    return {
        "dry_run": False,
        "zip_path": str(output),
        "manifest": manifest.to_dict(),
        "files": [entry.to_dict() for entry in entries],
    }


def list_backup_archive(zip_path: Path) -> Dict:
    """Return manifest and members from an existing backup zip without extracting it."""
    with zipfile.ZipFile(Path(zip_path), "r") as archive:
        names = archive.namelist()
        manifest = _read_manifest(archive) if MANIFEST_NAME in names else None
        return {
            "zip_path": str(zip_path),
            "manifest": manifest,
            "members": [_member_info(archive.getinfo(name)) for name in names],
        }


def restore_backup(zip_path: Path, target_data_dir: Path, dry_run: bool = False) -> Dict:
    """
    Restore a backup zip into target_data_dir.

    Archive member paths are validated before any write. This prevents zip slip
    and keeps restore output constrained to the allowed data subtrees.
    """
    target = Path(target_data_dir)
    with zipfile.ZipFile(Path(zip_path), "r") as archive:
        infos = archive.infolist()
        _validate_archive_members(infos)
        manifest = _read_manifest(archive)
        restored = [
            _member_info(info)
            for info in infos
            if not info.is_dir() and info.filename != MANIFEST_NAME
        ]
        if dry_run:
            return {
                "dry_run": True,
                "target_data_dir": str(target),
                "manifest": manifest,
                "files": restored,
            }

        for info in infos:
            if info.is_dir() or info.filename == MANIFEST_NAME:
                continue
            destination = _safe_destination(target, info.filename)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, destination.open("wb") as output:
                output.write(source.read())

    return {
        "dry_run": False,
        "target_data_dir": str(target),
        "manifest": manifest,
        "files": restored,
    }


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


def _collect_index_schema_versions(root: Path, entries: Iterable[BackupEntry]) -> Dict[str, Optional[int]]:
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


def _read_manifest(archive: zipfile.ZipFile) -> Dict:
    try:
        return json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
    except KeyError as exc:
        raise ValueError("Backup archive is missing manifest.json.") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Backup manifest is not valid UTF-8 JSON.") from exc


def _validate_archive_members(infos: Iterable[zipfile.ZipInfo]) -> None:
    names = [info.filename for info in infos]
    if MANIFEST_NAME not in names:
        raise ValueError("Backup archive is missing manifest.json.")
    for name in names:
        if name == MANIFEST_NAME or name.endswith("/"):
            continue
        _validate_member_path(name)
        if not _is_allowed_backup_path(name):
            raise ValueError(f"Backup member is outside allowed data paths: {name}")


def _validate_member_path(name: str) -> None:
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


def _is_allowed_backup_path(name: str) -> bool:
    return name in ALLOWED_BACKUP_FILES or any(name.startswith(f"{root}/") for root in ALLOWED_BACKUP_ROOTS)


def _safe_destination(target: Path, archive_name: str) -> Path:
    _validate_member_path(archive_name)
    destination = target / archive_name
    resolved_target = target.resolve()
    resolved_destination = destination.resolve()
    if resolved_destination != resolved_target and resolved_target not in resolved_destination.parents:
        raise ValueError(f"Backup member escapes target directory: {archive_name}")
    return destination


def _member_info(info: zipfile.ZipInfo) -> Dict:
    return {
        "path": info.filename,
        "size": info.file_size,
        "compressed_size": info.compress_size,
        "is_dir": info.is_dir(),
    }
