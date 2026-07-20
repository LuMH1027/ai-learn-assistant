import os
import tempfile
import unittest
import time
from pathlib import Path

from local_course_agent.config import normalize_config
from local_course_agent.uploads import (
    MAX_UPLOAD_FILE_BYTES,
    cleanup_chat_uploads,
    safe_upload_name,
    save_chat_upload,
    save_course_upload,
)


class ConfigAndUploadsTest(unittest.TestCase):
    def test_normalize_config_keeps_legacy_values_and_nests_ai(self):
        config = normalize_config(
            {
                "root_folder": "D:/Study",
                "ai": {
                    "base_url": "https://api.siliconflow.cn/v1",
                    "api_key": "test-key",
                    "model": "Pro/moonshotai/Kimi-K2.6",
                },
            }
        )

        self.assertEqual(config["root_folder"], "D:/Study")
        self.assertEqual(config["ai"]["provider"], "openai_compatible")
        self.assertEqual(config["ai"]["base_url"], "https://api.siliconflow.cn/v1")
        self.assertEqual(config["ai"]["model"], "Pro/moonshotai/Kimi-K2.6")
        self.assertTrue(config["mineru"]["auto"])
        self.assertFalse(config["web_search"]["enabled"])
        self.assertEqual(config["web_search"]["provider"], "mcp")

    def test_normalize_config_keeps_web_search_settings(self):
        config = normalize_config({
            "web_search": {
                "enabled": True,
                "mcp_url": "https://search.example/mcp",
                "tool_name": "web_search",
            }
        })

        self.assertTrue(config["web_search"]["enabled"])
        self.assertEqual(config["web_search"]["mcp_url"], "https://search.example/mcp")

    def test_safe_upload_name_removes_path_segments(self):
        self.assertEqual(safe_upload_name("../evil.pdf"), "evil.pdf")
        self.assertEqual(safe_upload_name("C:\\tmp\\note.md"), "note.md")

    def test_save_course_upload_copies_supported_file_into_drop_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "操作系统"
            course_dir.mkdir()

            saved = save_course_upload(course_dir, "chapter.md", b"# Chapter")

            self.assertEqual(saved.parent.name, "拖入资料")
            self.assertEqual(saved.read_bytes(), b"# Chapter")

    def test_save_chat_upload_accepts_screenshot_images(self):
        with tempfile.TemporaryDirectory() as tmp:
            saved = save_chat_upload(Path(tmp), "course-1", "screen.png", b"png-bytes")

            self.assertEqual(saved.parent.name, "course-1")
            self.assertEqual(saved.suffix, ".png")
            self.assertEqual(saved.read_bytes(), b"png-bytes")

    def test_save_upload_rejects_oversized_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            course_dir = Path(tmp) / "操作系统"
            course_dir.mkdir()

            with self.assertRaisesRegex(ValueError, "文件过大"):
                save_course_upload(course_dir, "chapter.md", b"x" * (MAX_UPLOAD_FILE_BYTES + 1))

    def test_chat_upload_cleanup_removes_oldest_extra_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "chat_uploads" / "course-1"
            target.mkdir(parents=True)
            for index in range(3):
                path = target / f"{index}.md"
                path.write_text("note", encoding="utf-8")
                timestamp = time.time() - (10 - index)
                path.touch()
                os.utime(path, (timestamp, timestamp))

            cleanup_chat_uploads(target, max_files=2, max_age_seconds=1000)

            self.assertEqual({path.name for path in target.iterdir()}, {"1.md", "2.md"})


if __name__ == "__main__":
    unittest.main()
