import tempfile
import unittest
from pathlib import Path

from local_course_agent.config import normalize_config
from local_course_agent.uploads import safe_upload_name, save_course_upload


class ConfigAndUploadsTest(unittest.TestCase):
    def test_normalize_config_keeps_legacy_values_and_nests_ai(self):
        config = normalize_config(
            {
                "root_folder": "D:/Study",
                "ollama_url": "http://127.0.0.1:11434",
                "ollama_model": "qwen2.5:7b",
            }
        )

        self.assertEqual(config["root_folder"], "D:/Study")
        self.assertEqual(config["ai"]["ollama_url"], "http://127.0.0.1:11434")
        self.assertEqual(config["ai"]["ollama_model"], "qwen2.5:7b")
        self.assertTrue(config["mineru"]["auto"])

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


if __name__ == "__main__":
    unittest.main()
