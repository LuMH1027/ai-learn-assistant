from __future__ import annotations

from .archive import build_manifest, create_backup, list_backup_archive
from .collectors import collect_backup_entries
from .restore import restore_backup
from .schema import (
    ALLOWED_BACKUP_FILES,
    ALLOWED_BACKUP_ROOTS,
    BACKUP_SCHEMA_VERSION,
    MANIFEST_NAME,
    BackupEntry,
    BackupManifest,
)


create_backup_archive = create_backup
restore_backup_archive = restore_backup


__all__ = [
    "ALLOWED_BACKUP_FILES",
    "ALLOWED_BACKUP_ROOTS",
    "BACKUP_SCHEMA_VERSION",
    "MANIFEST_NAME",
    "BackupEntry",
    "BackupManifest",
    "build_manifest",
    "collect_backup_entries",
    "create_backup",
    "create_backup_archive",
    "list_backup_archive",
    "restore_backup",
    "restore_backup_archive",
]
