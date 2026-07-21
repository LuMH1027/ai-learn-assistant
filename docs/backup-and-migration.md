# Backup and Migration

This module provides a minimal local backup/restore layer for generated course data.
It is exposed through a small CLI script and intentionally remains separate from
`store.py`, `server.py`, and the frontend.

## Scope

`local_course_agent.backup` archives only these paths under a data directory:

- `config.example.json`
- `course_memory/**`
- `indexes/**`

Runtime secrets such as `config.json`, SQLite files, uploads, caches, and unrelated files are excluded.

## API

```python
from pathlib import Path

from local_course_agent.backup import (
    collect_backup_entries,
    create_backup,
    list_backup_archive,
    restore_backup,
)

entries = collect_backup_entries(Path("data"))
preview = create_backup(Path("data"), Path("course-backup.zip"), dry_run=True)
result = create_backup(Path("data"), Path("course-backup.zip"))
listing = list_backup_archive(Path("course-backup.zip"))
restore_preview = restore_backup(Path("course-backup.zip"), Path("restored-data"), dry_run=True)
restore_result = restore_backup(Path("course-backup.zip"), Path("restored-data"))
```

`dry_run=True` never writes files. It returns the files that would be archived or restored.

## CLI

Create a backup zip:

```bash
python3 scripts/course_backup.py create --data-dir data --output course-backup.zip
```

`backup` is accepted as an alias for `create`:

```bash
python3 scripts/course_backup.py backup --data-dir data --output course-backup.zip
```

Preview a backup without writing the zip:

```bash
python3 scripts/course_backup.py create --data-dir data --output course-backup.zip --dry-run
```

Inspect an existing backup:

```bash
python3 scripts/course_backup.py list --backup course-backup.zip
```

Restore into a target data directory:

```bash
python3 scripts/course_backup.py restore --backup course-backup.zip --target restored-data
```

Preview restore without writing files:

```bash
python3 scripts/course_backup.py restore --backup course-backup.zip --target restored-data --dry-run
```

All commands write JSON to stdout. Invalid archives, missing files, and unsafe
restore members return a non-zero exit code and print the error to stderr.

## Manifest

Every backup zip contains `manifest.json` at the archive root:

```json
{
  "backup_schema_version": 1,
  "created_at": "2026-07-21T00:00:00+00:00",
  "source_data_dir": "data",
  "files": [
    {
      "path": "indexes/course-1.json",
      "size": 128,
      "sha256": "...",
      "kind": "index"
    }
  ],
  "index_schema_versions": {
    "indexes/course-1.json": 2
  },
  "migration": {
    "index_schema_target": null,
    "index_schema_migrations": []
  }
}
```

The `migration` object is reserved for future index schema migrations. A later integration can use it to record planned or completed transforms, for example from index schema `2` to `3`.

## Restore Safety

Restore validates all zip members before writing anything:

- the archive must contain `manifest.json`;
- member paths must be relative POSIX paths;
- absolute paths, backslashes, `..`, and normalized path changes are rejected;
- only `config.example.json`, `course_memory/**`, and `indexes/**` may be restored;
- extraction destinations are resolved under the requested target data directory.

This prevents zip slip and avoids accidentally restoring files outside the local data contract.

## Future Integration

The next slice can expose this module through a server endpoint or scheduled local
backup job. Before that integration, decide whether restore should merge into
existing course data, write into an empty target directory, or require a
pre-restore snapshot.
