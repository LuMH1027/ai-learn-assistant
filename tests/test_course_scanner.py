import tempfile
import unittest
from pathlib import Path

from local_course_agent.scanner import CourseCatalogCache, CourseScanner


class CourseScannerTest(unittest.TestCase):
    def test_first_level_folders_are_courses_and_keep_nested_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Operating Systems" / "week1").mkdir(parents=True)
            (root / "Operating Systems" / "week1" / "intro.pdf").write_bytes(b"%PDF-1.4")
            (root / "Operating Systems" / "notes.md").write_text("# Notes", encoding="utf-8")
            (root / "not-a-course.txt").write_text("ignored", encoding="utf-8")

            courses = CourseScanner(root).scan()

            self.assertEqual(len(courses), 1)
            self.assertEqual(courses[0]["name"], "Operating Systems")
            self.assertEqual(courses[0]["path"], str((root / "Operating Systems").resolve()))
            file_names = {node["name"] for node in courses[0]["children"]}
            self.assertIn("week1", file_names)
            self.assertIn("notes.md", file_names)

    def test_unsupported_files_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Math").mkdir()
            (root / "Math" / "chapter.pdf").write_bytes(b"%PDF-1.4")
            (root / "Math" / "video.mp4").write_bytes(b"binary")

            course = CourseScanner(root).scan()[0]
            names = {node["name"] for node in course["children"]}

            self.assertEqual(names, {"chapter.pdf"})

    def test_catalog_cache_reuses_scan_until_invalidated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "Math").mkdir()
            (root / "Math" / "chapter.pdf").write_bytes(b"%PDF-1.4")
            cache = CourseCatalogCache(ttl_seconds=60)

            first = cache.get(root)
            (root / "Physics").mkdir()
            (root / "Physics" / "motion.pdf").write_bytes(b"%PDF-1.4")
            cached = cache.get(root)
            cache.invalidate()
            refreshed = cache.get(root)

            self.assertEqual([course["name"] for course in first], ["Math"])
            self.assertIs(first, cached)
            self.assertEqual([course["name"] for course in refreshed], ["Math", "Physics"])


if __name__ == "__main__":
    unittest.main()
