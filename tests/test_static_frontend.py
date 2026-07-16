import tempfile
import unittest
from pathlib import Path

from local_course_agent.server import (
    PROJECT_ROOT,
    STATIC_DIR,
    frontend_build_error,
    resolve_static_path,
)


class StaticFrontendTest(unittest.TestCase):
    def test_static_directory_is_the_vite_build_output(self):
        self.assertEqual(STATIC_DIR, PROJECT_ROOT / "web" / "dist")

    def test_root_and_assets_resolve_inside_the_build_directory(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir).resolve()
            self.assertEqual(resolve_static_path("/", root), root / "index.html")
            self.assertEqual(
                resolve_static_path("/assets/app.js?cache=1", root),
                root / "assets" / "app.js",
            )

    def test_path_traversal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            self.assertIsNone(resolve_static_path("/../data/config.json", root))
            self.assertIsNone(resolve_static_path("/%2e%2e/data/config.json", root))

    def test_missing_build_message_is_actionable(self):
        message = frontend_build_error()
        self.assertIn("前端尚未构建", message)
        self.assertIn("start", message.lower())


if __name__ == "__main__":
    unittest.main()
