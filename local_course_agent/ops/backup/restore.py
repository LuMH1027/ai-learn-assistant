from __future__ import annotations

import zipfile
from pathlib import Path
from typing import Dict

from .schema import MANIFEST_NAME
from .validation import member_info, read_manifest, safe_destination, validate_archive_members


def restore_backup(zip_path: Path, target_data_dir: Path, dry_run: bool = False) -> Dict:
    """
    Restore a backup zip into target_data_dir.

    Archive member paths are validated before any write. This prevents zip slip
    and keeps restore output constrained to the allowed data subtrees.
    """
    target = Path(target_data_dir)
    with zipfile.ZipFile(Path(zip_path), "r") as archive:
        infos = archive.infolist()
        validate_archive_members(infos)
        manifest = read_manifest(archive)
        restored = [
            member_info(info)
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
            destination = safe_destination(target, info.filename)
            destination.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info, "r") as source, destination.open("wb") as output:
                output.write(source.read())

    return {
        "dry_run": False,
        "target_data_dir": str(target),
        "manifest": manifest,
        "files": restored,
    }
