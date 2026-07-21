from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from local_course_agent.ops.backup import (  # noqa: E402
    create_backup,
    list_backup_archive,
    restore_backup,
)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Create, inspect, and restore local course data backups.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", aliases=["backup"], help="Create a backup zip.")
    create_parser.add_argument("--data-dir", required=True, help="Course data directory to archive.")
    create_parser.add_argument("--output", required=True, help="Backup zip path to write.")
    create_parser.add_argument("--dry-run", action="store_true", help="Show files without writing the zip.")
    create_parser.set_defaults(handler=_handle_create)

    list_parser = subparsers.add_parser("list", help="List a backup zip manifest and members.")
    list_parser.add_argument("--backup", "--target", dest="backup", required=True, help="Backup zip path to inspect.")
    list_parser.set_defaults(handler=_handle_list)

    restore_parser = subparsers.add_parser("restore", help="Restore a backup zip into a data directory.")
    restore_parser.add_argument("--backup", required=True, help="Backup zip path to restore.")
    restore_parser.add_argument("--target", required=True, help="Target data directory to write.")
    restore_parser.add_argument("--dry-run", action="store_true", help="Show files without writing them.")
    restore_parser.set_defaults(handler=_handle_restore)

    args = parser.parse_args(argv)
    try:
        payload = args.handler(args)
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _handle_create(args) -> dict:
    return create_backup(Path(args.data_dir), Path(args.output), dry_run=args.dry_run)


def _handle_list(args) -> dict:
    return list_backup_archive(Path(args.backup))


def _handle_restore(args) -> dict:
    return restore_backup(Path(args.backup), Path(args.target), dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
