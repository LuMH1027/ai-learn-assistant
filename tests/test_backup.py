import json
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from local_course_agent.backup import (
    MANIFEST_NAME,
    collect_backup_entries,
    create_backup,
    list_backup_archive,
    restore_backup,
)
from scripts.course_backup import main as backup_cli_main


class BackupTest(unittest.TestCase):
    def test_backup_includes_only_allowed_data_and_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _sample_data_dir(Path(tmp) / "data")
            zip_path = Path(tmp) / "backup.zip"

            result = create_backup(root, zip_path)

            self.assertTrue(zip_path.exists())
            self.assertFalse(result["dry_run"])
            self.assertEqual(
                [item["path"] for item in result["files"]],
                [
                    "config.example.json",
                    "course_memory/course-1/memory.md",
                    "indexes/course-1.json",
                ],
            )
            self.assertEqual(result["manifest"]["index_schema_versions"], {"indexes/course-1.json": 2})
            self.assertIn("index_schema_target", result["manifest"]["migration"])

            with zipfile.ZipFile(zip_path, "r") as archive:
                self.assertEqual(
                    sorted(archive.namelist()),
                    [
                        "config.example.json",
                        "course_memory/course-1/memory.md",
                        "indexes/course-1.json",
                        MANIFEST_NAME,
                    ],
                )
                self.assertNotIn("config.json", archive.namelist())
                manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
                self.assertEqual(manifest["backup_schema_version"], 1)

    def test_dry_run_lists_files_without_writing_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _sample_data_dir(Path(tmp) / "data")
            zip_path = Path(tmp) / "backup.zip"

            entries = collect_backup_entries(root)
            result = create_backup(root, zip_path, dry_run=True)

            self.assertFalse(zip_path.exists())
            self.assertTrue(result["dry_run"])
            self.assertEqual([entry.path for entry in entries], [item["path"] for item in result["files"]])

    def test_restore_backup_writes_to_target_data_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = _sample_data_dir(Path(tmp) / "source")
            zip_path = Path(tmp) / "backup.zip"
            target = Path(tmp) / "restored"
            create_backup(source, zip_path)

            preview = restore_backup(zip_path, target, dry_run=True)
            restored = restore_backup(zip_path, target)

            self.assertTrue(preview["dry_run"])
            self.assertFalse(restored["dry_run"])
            self.assertEqual((target / "config.example.json").read_text(encoding="utf-8"), '{"debug": false}')
            self.assertEqual((target / "course_memory/course-1/memory.md").read_text(encoding="utf-8"), "memory")
            self.assertEqual(json.loads((target / "indexes/course-1.json").read_text(encoding="utf-8"))["schema_version"], 2)

    def test_list_backup_archive_returns_manifest_and_members(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = _sample_data_dir(Path(tmp) / "data")
            zip_path = Path(tmp) / "backup.zip"
            create_backup(root, zip_path)

            listing = list_backup_archive(zip_path)

            self.assertEqual(listing["manifest"]["backup_schema_version"], 1)
            self.assertIn(MANIFEST_NAME, [item["path"] for item in listing["members"]])

    def test_restore_rejects_zip_slip_member(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "bad.zip"
            target = Path(tmp) / "target"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(MANIFEST_NAME, "{}")
                archive.writestr("../escape.txt", "bad")

            with self.assertRaises(ValueError):
                restore_backup(zip_path, target)

            self.assertFalse((Path(tmp) / "escape.txt").exists())

    def test_restore_rejects_unexpected_archive_member(self):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "bad.zip"
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(MANIFEST_NAME, "{}")
                archive.writestr("config.json", "{}")

            with self.assertRaises(ValueError):
                restore_backup(zip_path, Path(tmp) / "target")

    def test_cli_create_list_and_restore_backup(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = _sample_data_dir(Path(tmp) / "source")
            zip_path = Path(tmp) / "course-backup.zip"
            target = Path(tmp) / "restored"

            create_code, create_out, create_err = _run_cli(
                "create",
                "--data-dir",
                str(source),
                "--output",
                str(zip_path),
            )
            list_code, list_out, list_err = _run_cli("list", "--backup", str(zip_path))
            restore_code, restore_out, restore_err = _run_cli(
                "restore",
                "--backup",
                str(zip_path),
                "--target",
                str(target),
            )

            self.assertEqual(create_code, 0, create_err)
            self.assertTrue(zip_path.exists())
            self.assertEqual(json.loads(create_out)["manifest"]["backup_schema_version"], 1)
            self.assertEqual(list_code, 0, list_err)
            self.assertIn(MANIFEST_NAME, [item["path"] for item in json.loads(list_out)["members"]])
            self.assertEqual(restore_code, 0, restore_err)
            self.assertEqual(json.loads(restore_out)["target_data_dir"], str(target))
            self.assertEqual((target / "course_memory/course-1/memory.md").read_text(encoding="utf-8"), "memory")

    def test_cli_backup_alias_and_dry_run_do_not_write_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = _sample_data_dir(Path(tmp) / "source")
            zip_path = Path(tmp) / "course-backup.zip"

            code, out, err = _run_cli(
                "backup",
                "--data-dir",
                str(source),
                "--output",
                str(zip_path),
                "--dry-run",
            )

            self.assertEqual(code, 0, err)
            payload = json.loads(out)
            self.assertTrue(payload["dry_run"])
            self.assertFalse(zip_path.exists())

    def test_cli_returns_nonzero_for_invalid_archive(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, out, err = _run_cli("list", "--backup", str(Path(tmp) / "missing.zip"))

            self.assertEqual(code, 1)
            self.assertEqual(out, "")
            self.assertIn("error:", err)


def _sample_data_dir(root: Path) -> Path:
    (root / "course_memory/course-1").mkdir(parents=True)
    (root / "indexes").mkdir(parents=True)
    root.mkdir(parents=True, exist_ok=True)
    (root / "config.example.json").write_text('{"debug": false}', encoding="utf-8")
    (root / "config.json").write_text('{"secret": true}', encoding="utf-8")
    (root / "course_memory/course-1/memory.md").write_text("memory", encoding="utf-8")
    (root / "indexes/course-1.json").write_text(
        json.dumps({"schema_version": 2, "chunks": []}, ensure_ascii=False),
        encoding="utf-8",
    )
    return root


def _run_cli(*argv: str):
    stdout = StringIO()
    stderr = StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = backup_cli_main(list(argv))
    return code, stdout.getvalue(), stderr.getvalue()


if __name__ == "__main__":
    unittest.main()
