from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, Optional

from .collectors import collect_backup_entries, collect_index_schema_versions
from .schema import BACKUP_SCHEMA_VERSION, MANIFEST_NAME, BackupEntry, BackupManifest
from .validation import member_info, read_manifest


def build_manifest(data_dir: Path, entries: Optional[Iterable[BackupEntry]] = None) -> BackupManifest:
    root = Path(data_dir)
    file_entries = list(entries) if entries is not None else collect_backup_entries(root)
    return BackupManifest(
        backup_schema_version=BACKUP_SCHEMA_VERSION,
        created_at=datetime.now(timezone.utc).isoformat(),
        source_data_dir=str(root),
        files=file_entries,
        index_schema_versions=collect_index_schema_versions(root, file_entries),
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
        manifest = read_manifest(archive) if MANIFEST_NAME in names else None
        return {
            "zip_path": str(zip_path),
            "manifest": manifest,
            "members": [member_info(archive.getinfo(name)) for name in names],
        }
