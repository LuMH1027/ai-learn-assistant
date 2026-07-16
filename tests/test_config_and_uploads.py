import tempfile
import unittest
from pathlib import Path

from local_course_agent.config import normalize_config
from local_course_agent.uploads import safe_upload_name, save_chat_upload, save_course_upload


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


if __name__ == "__main__":
    unittest.main()
