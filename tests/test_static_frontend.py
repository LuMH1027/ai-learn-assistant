import tempfile
import unittest
from pathlib import Path

from local_course_agent.server import (
    PROJECT_ROOT,
    STATIC_DIR,
    frontend_build_error,
    is_frontend_entry,
    parse_course_route,
    resolve_static_path,
    static_cache_control,
)


class StaticFrontendTest(unittest.TestCase):
    def test_index_is_never_cached_but_hashed_assets_are_immutable(self):
        self.assertEqual(static_cache_control("/"), "no-store, max-age=0")
        self.assertEqual(static_cache_control("/index.html"), "no-store, max-age=0")
        self.assertEqual(
            static_cache_control("/assets/index-content-hash.js"),
            "public, max-age=31536000, immutable",
        )
        self.assertIsNone(static_cache_control("/api/config"))
        self.assertTrue(is_frontend_entry("/?refresh=1"))
        self.assertTrue(is_frontend_entry("/index.html"))
        self.assertFalse(is_frontend_entry("/assets/index.js"))

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

    def test_course_api_routes_are_parsed_centrally(self):
        self.assertEqual(parse_course_route("/api/courses/os-1/messages"), ("os-1", "messages"))
        self.assertEqual(parse_course_route("/api/courses/os-1/index/jobs"), ("os-1", "index/jobs"))
        self.assertEqual(parse_course_route("/api/config"), None)


if __name__ == "__main__":
    unittest.main()
