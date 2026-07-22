from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


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
